"""LBU Agent 服务入口。

启动:  uv run uvicorn main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 服务启动即预热 agent（构建 LangGraph 图 + 加载模型配置），首个请求不再等待
    from app.agent import build_agent

    build_agent()
    yield


app = FastAPI(
    title="LBU Agent",
    description="LinkBetweenUs 的 AI 智能助手服务（LangChain + LangGraph + Ollama）",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
