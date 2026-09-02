"""Agent HTTP API。

响应统一遵循 LinkBetweenUs 的 Result 约定 {code, message, data}。
LBU_agent 是独立于后端 Dify 方案的 agent 服务。
"""

import logging
import time

import httpx
from fastapi import APIRouter
from langchain_core.messages import HumanMessage

from app.agent import build_agent, extract_final_answer, get_tools
from app.agent.memory import memory
from app.config import get_settings
from app.schemas import (
    ChatData,
    ChatRequest,
    HealthData,
    HistoryMessage,
    Result,
    ToolInfo,
)
from app.storage import storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/chat", response_model=Result[ChatData])
async def chat(req: ChatRequest) -> Result[ChatData]:
    """对话入口：message + 可选 thread_id，返回回复与本次会话 ID。

    thread_id 即上下文记忆键：同一用户后续请求传回同一个 thread_id 即可延续对话。
    """
    config = memory.config_for(req.thread_id)
    thread_id = config["configurable"]["thread_id"]
    started_at_ms = time.time() * 1000
    try:
        result = await build_agent().ainvoke(
            {"messages": [HumanMessage(content=req.message)]},
            config=config,
        )
    except Exception as e:  # noqa: BLE001 —— 统一转 Result 错误，避免 500 裸堆栈
        # 回滚本次失败 run 写入的 checkpoint，避免未回复的用户消息残留在上下文里
        try:
            await memory.rollback(thread_id, started_at_ms)
        except Exception as re:  # noqa: BLE001 —— 回滚失败只记日志
            logger.warning("失败请求回滚失败: thread_id=%s, error=%s", thread_id, re)
        return Result.error(500, f"Agent 调用失败: {e}")

    reply = extract_final_answer(result)
    try:
        await storage.save_exchange(thread_id, req.message, reply)
    except Exception as e:  # noqa: BLE001 —— 历史落库失败只记日志，不影响对话结果
        logger.warning("历史记录落库失败: thread_id=%s, error=%s", thread_id, e)
    try:
        await memory.compact(thread_id)
    except Exception as e:  # noqa: BLE001 —— 压缩失败只记日志，不影响对话结果
        logger.warning("会话 checkpoint 压缩失败: thread_id=%s, error=%s", thread_id, e)
    return Result.ok(ChatData(reply=reply, thread_id=thread_id))


@router.delete("/conversation/{thread_id}", response_model=Result[None])
async def clear_conversation(thread_id: str) -> Result[None]:
    """清空指定会话的上下文与历史记录。"""
    await memory.clear(thread_id)
    try:
        await storage.clear(thread_id)
    except Exception as e:  # noqa: BLE001 —— 历史清理失败只记日志
        logger.warning("历史记录清理失败: thread_id=%s, error=%s", thread_id, e)
    return Result.ok(None)


@router.get("/history/{thread_id}", response_model=Result[list[HistoryMessage]])
async def get_history(thread_id: str) -> Result[list[HistoryMessage]]:
    """查询指定会话的历史记录（仅展示用，按时间正序）。"""
    try:
        messages = await storage.list_history(thread_id)
    except Exception as e:  # noqa: BLE001
        return Result.error(500, f"查询历史失败: {e}")
    return Result.ok(messages)


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
