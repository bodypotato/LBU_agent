"""内置工具：时间查询、后端健康探测、RAG 产品文档检索。"""

from datetime import datetime

import httpx
from langchain_core.tools import tool

from app.agent.rag import rag
from app.config import get_settings


@tool
def get_current_time() -> str:
    """获取当前日期和时间（北京时区为 UTC+8，返回 ISO 格式，不含时区换算）。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


@tool
def check_lbu_backend_health() -> str:
    """探测 LinkBetweenUs 后端服务是否在线可达。

    返回后端地址及连通状态，供回答"服务是否正常"类问题时使用。
    """
    settings = get_settings()
    base = settings.lbu_backend_base_url.rstrip("/")
    try:
        resp = httpx.get(f"{base}/error", timeout=3.0)
        # /error 是后端白名单路径，无 JWT 也可访问，连通即代表服务在线
        return f"LinkBetweenUs 后端（{base}）在线，HTTP 状态码 {resp.status_code}。"
    except httpx.HTTPError:
        return f"LinkBetweenUs 后端（{base}）当前不可达，服务可能未启动。"


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
    get_current_time,
    check_lbu_backend_health,
    search_lbu_docs,
]
