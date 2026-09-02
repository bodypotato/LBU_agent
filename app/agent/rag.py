"""RAG：基于 docs/LBU.md 的产品文档检索增强（父子文档模式）。

层级设计：
- 父文档：MarkdownHeaderTextSplitter 按标题层级（#/##/###/####）切分，
  一节一个父文档，携带标题路径元数据，作为喂给 LLM 的完整上下文单元。
- 子文档：每个父文档用 RecursiveCharacterTextSplitter 按 200 字 chunk /
  50 字重合切分，写入 Chroma 向量库做语义检索。检索时用子文档精确命中，
  再映射回父文档去重返回——召回精度与上下文完整性兼得。
- 增量重建：以 LBU.md 的 md5 作为集合元数据，文件未变化时直接复用
  Chroma 中已有向量（跳过重复 embedding），只重建内存中的父文档映射。

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
        """加载 LBU.md、切分并构建 Chroma 向量索引（幂等，按内容 hash 增量重建）。

        内部包含 embedding 等阻塞型 CPU 工作，仅在服务启动阶段调用，
        不影响运行期事件循环。
        """
        settings = get_settings()
        doc_path = Path(settings.lbu_doc_path)
        if not doc_path.exists():
            logger.warning("RAG 文档不存在，检索不可用: %s", doc_path)
            return

        text = doc_path.read_text(encoding="utf-8")
        source_hash = hashlib.md5(text.encode("utf-8")).hexdigest()

        self._embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model_name,
            model_kwargs={
                "device": settings.embedding_device,
                "trust_remote_code": True,  # Qwen3-Embedding 需要远程代码
            },
        )
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._rebuild_parents(text)

        # 文档未变化且已有向量 → 直接复用，不重复 embedding
        existing = self._client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"source_hash": source_hash}
        )
        if existing.metadata.get("source_hash") == source_hash and existing.count() > 0:
            self._collection = existing
            logger.info("RAG 复用已有向量索引（%d 个子文档）", existing.count())
            return

        # 文档变化（或首次构建）→ 重建集合
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"source_hash": source_hash}
        )

        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHILD_CHUNK_SIZE,
            chunk_overlap=CHILD_CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )
        children: list[tuple[str, Document]] = []
        for parent_id, parent in self._parents.items():
            for child in child_splitter.split_documents([parent]):
                children.append((parent_id, child))

        logger.info("RAG 开始构建索引：父文档 %d 个，子文档 %d 个", len(self._parents), len(children))
        self._collection.add(
            ids=[f"{pid}:{i}" for i, (pid, _) in enumerate(children)],
            documents=[c.page_content for _, c in children],
            # 子文档只携带 parent_id，检索时映射回父文档
            metadatas=[{"parent_id": pid} for pid, _ in children],
            embeddings=self._embeddings.embed_documents(
                [c.page_content for _, c in children]
            ),
        )
        logger.info("RAG 索引构建完成（%d 个子文档）", len(children))

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
            if parent_id and parent_id not in seen and parent_id in self._parents:
                seen.add(parent_id)
                parents.append(self._parents[parent_id])
        return parents[: settings.rag_top_k]

    def _rebuild_parents(self, text: str) -> None:
        """按 Markdown 标题切分父文档，以确定性编号 p0/p1/... 建立映射。"""
        docs = MarkdownHeaderTextSplitter(
            headers_to_split_on=HEADERS_TO_SPLIT_ON
        ).split_text(text)
        parents: dict[str, Document] = {}
        for i, doc in enumerate(docs):
            parents[f"p{i}"] = Document(
                page_content=doc.page_content.strip(),
                metadata={
                    "title": self._doc_title(doc),
                    **{k: v for k, v in doc.metadata.items() if v},
                },
            )
        self._parents = parents

    @staticmethod
    def _doc_title(doc: Document) -> str:
        """用各级标题拼出文档标题，如「核心功能 / 2. 好友系统 / 添加好友」。"""
        parts = [
            str(doc.metadata[h])
            for h in ("h1", "h2", "h3", "h4")
            if doc.metadata.get(h)
        ]
        return " / ".join(parts) if parts else "LBU 产品文档"


rag = RagStore()
