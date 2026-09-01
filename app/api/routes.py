"""Agent HTTP API。

响应统一遵循 LinkBetweenUs 的 Result 约定 {code, message, data}，
接口语义对齐后端 Dify 方案（对话 / 清空上下文），便于后续直接替换。
"""

import httpx
from fastapi import APIRouter

from app.agent import build_agent, extract_final_answer, get_tools
from app.agent.memory import memory
from app.config import get_settings
from app.schemas import ChatData, ChatRequest, HealthData, Result, ToolInfo

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/chat", response_model=Result[ChatData])
async def chat(req: ChatRequest) -> Result[ChatData]:
    """对话入口：message + 可选 thread_id，返回回复与本次会话 ID。

    thread_id 即上下文记忆键：同一用户后续请求传回同一个 thread_id 即可延续对话。
    """
    config = memory.config_for(req.thread_id)
    try:
        result = await build_agent().ainvoke(
            {"messages": [{"role": "user", "content": req.message}]},
            config=config,
        )
    except Exception as e:  # noqa: BLE001 —— 统一转 Result 错误，避免 500 裸堆栈
        return Result.error(500, f"Agent 调用失败: {e}")

    reply = extract_final_answer(result)
    thread_id = config["configurable"]["thread_id"]
    return Result.ok(ChatData(reply=reply, thread_id=thread_id))


@router.delete("/conversation/{thread_id}", response_model=Result[None])
async def clear_conversation(thread_id: str) -> Result[None]:
    """清空指定会话的上下文（对齐后端 /api/dify/conversation）。"""
    memory.clear(thread_id)
    return Result.ok(None)


@router.get("/tools", response_model=Result[list[ToolInfo]])
async def list_tools() -> Result[list[ToolInfo]]:
    """列出当前注册给 agent 的全部工具。"""
    tools = [
        ToolInfo(name=t.name, description=t.description or "")
        for t in get_tools()
    ]
    return Result.ok(tools)


@router.get(
    "/health",
    response_model=Result[HealthData],
    responses={200: {"model": Result[HealthData]}},
)
async def health() -> Result[HealthData]:
    """健康检查：agent 配置与 Ollama 连通性。"""
    settings = get_settings()
    try:
        httpx.get(f"{settings.ollama_native_url}/api/tags", timeout=3.0)
        reachable = True
    except httpx.HTTPError:
        reachable = False

    return Result.ok(
        HealthData(
            status="ok" if reachable else "degraded",
            model=settings.ollama_model,
            ollama_base_url=settings.ollama_base_url,
            ollama_reachable=reachable,
        )
    )


__all__ = ["router"]
