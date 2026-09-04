"""内置工具：RAG 产品文档检索（依赖 Chroma/embedding，留在 agent 进程）。

时间查询、后端健康探测等通用能力已迁入 lbu-tools MCP 服务（app/mcp/）。
"""

from langchain_core.tools import tool

from app.agent.rag import rag


@tool
def search_lbu_docs(query: str) -> str:
    """检索 LinkBetweenUs（LBU）产品文档 docs/LBU.md 中的相关内容。

    当用户询问 LBU 产品的功能、使用方法、操作流程、常见问题等产品相关问题时，
    必须先调用本工具检索产品文档，回答严格以检索结果为准；
    文档中没有检索到的内容要如实告知用户，不要凭记忆编造。
    """
    try:
        parents = rag.search(query)
    except Exception as e:  # noqa: BLE001 —— RAG 未就绪/模型异常时降级为提示
        return f"产品文档检索暂不可用（{e}）。请如实告知用户稍后再试，不要编造产品信息。"
    if not parents:
        return "未在 LBU 产品文档中检索到相关内容。请如实告知用户该问题在文档中没有记载，不要编造。"
    parts = []
    for doc in parents:
        title = doc.metadata.get("title") or "LBU 产品文档"
        parts.append(f"【{title}】\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


BUILTIN_TOOLS: list = [
    search_lbu_docs,
]
