"""LBU Agent 服务入口。

启动:  uv run uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动顺序：先建立 Redis checkpointer 连接，再构建 LangGraph 图（图编译时绑定 checkpointer）
    from app.agent import build_agent
    from app.agent.memory import memory
    from app.storage import storage

    await memory.setup()
    try:
        await storage.setup()
    except Exception as e:  # noqa: BLE001 —— MySQL 暂不可用时服务照常启动，历史功能降级
        logging.getLogger(__name__).warning(
            "MySQL 历史存储初始化失败（历史记录暂不可用）: %s", e
        )
    build_agent()
    yield


app = FastAPI(
    title="LBU Agent",
    description="LinkBetweenUs 的 AI 智能助手服务（LangChain + LangGraph + Ollama）",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
