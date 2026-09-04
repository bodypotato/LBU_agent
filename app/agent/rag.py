"""RAG：基于 docs/ 目录的产品文档检索增强（父子文档模式，多文档分类存储）。

层级设计：
- 父文档：MarkdownHeaderTextSplitter 按标题层级（#/##/###/####）切分，
  一节一个父文档，携带标题路径与分类元数据，作为喂给 LLM 的完整上下文单元。
- 子文档：每个父文档用 RecursiveCharacterTextSplitter 按 200 字 chunk /
  50 字重合切分，写入 Chroma 向量库做语义检索。检索时用子文档精确命中，
  再映射回父文档去重返回——召回精度与上下文完整性兼得。
- 多文档分类：RAG_DOC_DIR 下全部 .md 均为文档源，子文档 metadata 统一携带
  source（文件相对路径）与 category（所在目录），检索默认全库、后续可按
  分类过滤。父文档内存映射同样带分类，方便追踪来源。
- 按文件增量：每个文件的 md5 存在各自子文档的 hash 元数据里，启动时对比——
  新增/变化的文件只重建自己，删除的文件同步清理向量，互不覆盖。

生命周期：服务启动时（main.py lifespan）调用 `await rag.setup()`；
初始化失败（模型未下载 / Chroma 异常）服务照常启动，检索工具降级返回提示。
首次运行会从 HuggingFace 下载 embedding 模型（EMBEDDING_MODEL_NAME），耗时较长。
"""

import hashlib
import logging
from pathlib import Path

import chromadb
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "lbu_docs"
CHILD_CHUNK_SIZE = 200
CHILD_CHUNK_OVERLAP = 50
HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
]


class RagStore:
    """持有 Chroma 集合、embedding 模型与父文档映射，提供文档检索。"""

    def __init__(self) -> None:
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None
        self._embeddings: HuggingFaceEmbeddings | None = None
        self._parents: dict[str, Document] = {}  # parent_id -> 父文档

    @property
    def ready(self) -> bool:
        """索引是否就绪（setup 成功过）。"""
        return self._collection is not None

    async def setup(self) -> None:
        """扫描 RAG_DOC_DIR 下的全部 .md，按文件增量构建 Chroma 索引（幂等）。

        内部包含 embedding 等阻塞型 CPU 工作，仅在服务启动阶段调用，
        不影响运行期事件循环。
        """
        settings = get_settings()
        doc_dir = Path(settings.rag_doc_dir)
        if not doc_dir.exists():
            logger.warning("RAG 文档目录不存在，检索不可用: %s", doc_dir)
            return

        files: dict[str, str] = {}  # 文件相对路径 -> 文本内容
        for path in sorted(doc_dir.rglob("*.md")):
            files[path.relative_to(doc_dir).as_posix()] = path.read_text(encoding="utf-8")
        if not files:
            logger.warning("RAG 文档目录下没有 .md 文件，检索不可用: %s", doc_dir)
            return

        self._embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model_name,
            model_kwargs={
                "device": settings.embedding_device,
                "trust_remote_code": True,  # Qwen3-Embedding 需要远程代码
            },
        )
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)

        # 盘点已入库的 source -> hash；旧版数据没有 source 元数据则整体重建
        index_state: dict[str, str] = {}
        legacy = False
        existing = self._collection.get(limit=10000, include=["metadatas"])
        for meta in existing.get("metadatas") or []:
            src = meta.get("source")
            if not src:
                legacy = True
                break
            index_state[str(src)] = str(meta.get("hash") or "")
        if legacy:
            logger.info("检测到旧版索引结构（无 source 分类），整体重建")
            self._client.delete_collection(COLLECTION_NAME)
            self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)
            index_state = {}

        # 按文件增量：新增/变化的文件只重建自己，不影响其他文件
        for rel, text in files.items():
            source_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
            if index_state.get(rel) == source_hash:
                continue
            self._index_file(rel, text, source_hash)
        # 文件已删除的，同步清理其残留向量
        for src in set(index_state) - set(files):
            self._collection.delete(where={"source": src})
            logger.info("RAG 清理已删除文件的向量: %s", src)

        self._rebuild_parents(files)

    def search(self, query: str) -> list[Document]:
        """检索与 query 最相关的父文档（子文档命中 → 映射回父文档，按命中序去重）。"""
        if not self.ready:
            raise RuntimeError("RAG 未初始化：请先 await rag.setup()（服务启动时自动执行）")
        settings = get_settings()
        query_embedding = self._embeddings.embed_query(query)
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=settings.rag_top_k * 2,  # 子文档命中数放大，提高父文档覆盖
            include=["metadatas"],
        )
        seen: set[str] = set()
        parents: list[Document] = []
        for meta in result["metadatas"][0]:
            parent_id = meta.get("parent_id")
            # chroma 类型标注里 metadata 值可能是任意 JSON 类型（含不可哈希的 list），
            # 这里显式收窄为 str（实际写入的 parent_id 一定是 str）
            if isinstance(parent_id, str) and parent_id not in seen and parent_id in self._parents:
                seen.add(parent_id)
                parents.append(self._parents[parent_id])
        return parents[: settings.rag_top_k]

    def _index_file(self, rel: str, text: str, source_hash: str) -> None:
        """切分单个文件并写入向量：先清掉该文件旧子文档，再写入新子文档。"""
        self._collection.delete(where={"source": rel})  # 幂等清理
        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHILD_CHUNK_SIZE,
            chunk_overlap=CHILD_CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )
        children: list[tuple[str, Document]] = []
        for parent_id, parent in self._split_parents(rel, text).items():
            for child in child_splitter.split_documents([parent]):
                children.append((parent_id, child))
        if not children:
            logger.warning("RAG 文件切分后没有子文档: %s", rel)
            return
        self._collection.add(
            ids=[f"{pid}:{i}" for i, (pid, _) in enumerate(children)],
            documents=[c.page_content for _, c in children],
            # 子文档统一携带四个键（全库一致，Chroma 才能按 where 过滤）：
            # parent_id 映射父文档、source 文件路径、category 所在目录、hash 增量比对
            metadatas=[
                {
                    "parent_id": pid,
                    "source": rel,
                    "category": _category_of(rel),
                    "hash": source_hash,
                }
                for pid, _ in children
            ],
            embeddings=self._embeddings.embed_documents(
                [c.page_content for _, c in children]
            ),
        )
        logger.info("RAG 索引文件 %s（%d 个子文档）", rel, len(children))

    def _rebuild_parents(self, files: dict[str, str]) -> None:
        """重建内存中的父文档映射（所有文件，供检索时映射回父文档）。"""
        parents: dict[str, Document] = {}
        for rel, text in files.items():
            parents.update(self._split_parents(rel, text))
        self._parents = parents

    def _split_parents(self, rel: str, text: str) -> dict[str, Document]:
        """按 Markdown 标题切分父文档，parent_id = {source}#p{i}，全局唯一。"""
        docs = MarkdownHeaderTextSplitter(
            headers_to_split_on=HEADERS_TO_SPLIT_ON
        ).split_text(text)
        parents: dict[str, Document] = {}
        for i, doc in enumerate(docs):
            pid = f"{rel}#p{i}"
            parents[pid] = Document(
                page_content=doc.page_content.strip(),
                metadata={
                    "title": self._doc_title(doc),
                    "source": rel,
                    "category": _category_of(rel),
                    **{k: v for k, v in doc.metadata.items() if v},
                },
            )
        return parents

    @staticmethod
    def _doc_title(doc: Document) -> str:
        """用各级标题拼出文档标题，如「核心功能 / 2. 好友系统 / 添加好友」。"""
        parts = [
            str(doc.metadata[h])
            for h in ("h1", "h2", "h3", "h4")
            if doc.metadata.get(h)
        ]
        return " / ".join(parts) if parts else "LBU 产品文档"


def _category_of(rel: str) -> str:
    """取文件所在目录作为分类（顶层文件分类为空字符串）。"""
    parent = Path(rel).parent
    return "" if str(parent) == "." else parent.as_posix()


rag = RagStore()
