"""请求/响应模型。

响应统一采用 LinkBetweenUs 后端的 Result 约定：
    {"code": 200, "message": "ok", "data": {...}}
成功 code=200，失败 code=4xx/5xx —— 与 Spring Boot 端的 Result<T> 保持一致，
方便后端 / 前端直接对接。
"""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    code: int = 200
    message: str = "ok"
    data: T | None = None

    @classmethod
    def ok(cls, data: T) -> "Result[T]":
        return cls(code=200, message="ok", data=data)

    @classmethod
    def error(cls, code: int, message: str) -> "Result[None]":
        return cls(code=code, message=message, data=None)


# ---- /api/agent/chat ----

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="用户消息")
    thread_id: str | None = Field(
        default=None,
        description="会话 ID（对应 LBU 中每个用户与 ai_bot 的对话）。不传则自动新建。",
    )


class ChatData(BaseModel):
    reply: str = Field(description="agent 最终回复")
    thread_id: str = Field(description="本次对话使用的会话 ID，后续请求带上以延续上下文")


# ---- /api/agent/history/{thread_id} ----

class HistoryMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # 端点直接返回 ORM 对象

    role: str = Field(description="消息角色：user / assistant")
    content: str = Field(description="消息内容")
    create_time: datetime = Field(description="写入时间")


# ---- /api/agent/health ----

class HealthData(BaseModel):
    status: str
    model: str
    ollama_base_url: str
    ollama_reachable: bool
    mcp_reachable: bool


# ---- /api/agent/tools ----

class ToolInfo(BaseModel):
    name: str
    description: str
