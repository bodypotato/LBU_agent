"""LBU Agent 服务入口。

启动:  uv run uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

# uvicorn 默认根日志级别为 WARNING，这里放开 INFO，让应用模块的
# logger.info（RAG 构建状态、MySQL 初始化等）在启动日志中可见
logging.basicConfig(level=logging.INFO)

from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动顺序：先建立 Redis checkpointer 连接，再拉起 MCP 工具服务，
    # 最后构建 LangGraph 图（图编译时绑定 checkpointer 并加载 MCP 工具）
    from app.agent import build_agent
    from app.agent.mcp_client import clear_mcp_tools_cache, close_mcp_client
    from app.agent.memory import memory
    from app.agent.rag import rag
    from app.mcp import start_mcp_server, stop_mcp_server
    from app.storage import storage

    await memory.setup()
    try:
        await storage.setup()
    except Exception as e:  # noqa: BLE001 —— MySQL 暂不可用时服务照常启动，历史功能降级
        logging.getLogger(__name__).warning(
            "MySQL 历史存储初始化失败（历史记录暂不可用）: %s", e
        )
    try:
        await rag.setup()
    except Exception as e:  # noqa: BLE001 —— RAG 暂不可用时服务照常启动，检索工具降级
        logging.getLogger(__name__).warning(
            "RAG 初始化失败（产品文档检索暂不可用）: %s", e
        )
    mcp_proc = await start_mcp_server()  # MCP 已在运行则复用；失败只降级不影响主服务
    clear_mcp_tools_cache()  # 确保按最新连接状态加载 MCP 工具
    await build_agent()
    try:
        yield
    finally:
        await close_mcp_client()
        stop_mcp_server(mcp_proc)


app = FastAPI(
    title="LBU Agent",
    description="LinkBetweenUs 的 AI 智能助手服务（LangChain + LangGraph + Ollama）",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
