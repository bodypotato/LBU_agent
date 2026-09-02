"""会话记忆：以 thread_id 为粒度的对话上下文管理，持久化到 Redis。

- checkpointer 使用 AsyncRedisSaver（langgraph-checkpoint-redis），会话历史落盘，
  服务重启后上下文不丢。Redis 连接参数（REDIS_URL / REDIS_PASSWORD）在 .env 中。
- 与 LinkBetweenUs 后端共用 Redis 实例，key 均带 checkpoint 前缀，互不干扰。
- thread_id 对应「用户 account × ai_bot」的独立对话，同一用户连续对话传同一个
  thread_id 即延续上下文。
- clear(thread_id) 支持按会话清空上下文。

生命周期：服务启动时（main.py lifespan）先 `await memory.setup()` 建立连接，
再编译 agent 图；首次调用前未 setup 会抛出明确错误。
"""

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.redis import AsyncRedisSaver

from app.config import get_settings

DEFAULT_THREAD_ID = "default"


class ConversationMemory:
    """持有全局 AsyncRedisSaver，支持按 thread_id 查询 / 清空历史。"""

    def __init__(self) -> None:
        self._saver: AsyncRedisSaver | None = None

    @property
    def checkpointer(self) -> AsyncRedisSaver:
        if self._saver is None:
            raise RuntimeError(
                "会话记忆未初始化：请先 await memory.setup()（服务启动时自动执行）"
            )
        return self._saver

    async def setup(self) -> None:
        """建立 Redis 连接并初始化 checkpointer（幂等）。"""
        if self._saver is not None:
            return
        settings = get_settings()
        saver = AsyncRedisSaver(redis_url=settings.redis_dsn)
        await saver.asetup()
        self._saver = saver

    async def clear(self, thread_id: str) -> None:
        """清空指定会话的上下文（幂等）。"""
        await self.checkpointer.adelete_thread(thread_id)

    def config_for(self, thread_id: str | None) -> RunnableConfig:
        """构造 invoke 使用的 config，thread_id 为空时使用默认会话。"""
        return {"configurable": {"thread_id": thread_id or DEFAULT_THREAD_ID}}


memory = ConversationMemory()
