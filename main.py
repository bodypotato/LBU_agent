"""LBU Agent 服务入口。

启动:  uv run uvicorn main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动顺序：先建立 Redis checkpointer 连接，再构建 LangGraph 图（图编译时绑定 checkpointer）
    from app.agent import build_agent
    from app.agent.memory import memory

    await memory.setup()
    build_agent()
    yield


app = FastAPI(
    title="LBU Agent",
    description="LinkBetweenUs 的 AI 智能助手服务（LangChain + LangGraph + Ollama）",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
