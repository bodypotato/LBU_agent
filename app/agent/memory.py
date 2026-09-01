"""会话记忆：以 thread_id 为粒度的对话上下文管理。

- checkpointer 使用 InMemorySaver（进程内）。地基阶段先跑通，后续可平滑替换为
  RedisSaver —— LinkBetweenUs 后端本就依赖 Redis，部署环境天然具备。
- thread_id 对应「用户 account × ai_bot」的独立对话，同一用户连续对话传同一个
  thread_id 即延续上下文。
- clear(thread_id) 支持按会话清空上下文。
"""

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

DEFAULT_THREAD_ID = "default"


class ConversationMemory:
    """持有全局 checkpointer，支持按 thread_id 查询 / 清空历史。"""

    def __init__(self) -> None:
        self._checkpointer = InMemorySaver()

    @property
    def checkpointer(self) -> InMemorySaver:
        return self._checkpointer

    def clear(self, thread_id: str) -> None:
        """清空指定会话的上下文（幂等）。"""
        self._checkpointer.delete_thread(thread_id)

    def config_for(self, thread_id: str | None) -> RunnableConfig:
        """构造 invoke 使用的 config，thread_id 为空时使用默认会话。"""
        return {"configurable": {"thread_id": thread_id or DEFAULT_THREAD_ID}}


memory = ConversationMemory()
