"""历史对话存储：MySQL 落库，仅用于展示历史，不参与 agent 上下文。

- 与 LinkBetweenUs 后端共用 MySQL 实例（MYSQL_* 配置在 .env），
  表 LBU_Agent_Message 独立于后端的 LBU_Message，互不干扰。
- 每次 /chat 成功后写入两条记录（user / assistant），写入失败只记日志，
  不影响对话主流程；上下文仍由 Redis checkpointer（agent/memory.py）管理，
  两者职责分离。
- 每条记录以 thread_id 关联会话，按自增 id 排序即时间序。

生命周期：服务启动时（main.py lifespan）调用 `await storage.setup()` 建连接
并自动建表（幂等）；MySQL 暂不可用时启动不中断，仅历史功能降级。
"""

import logging
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """LBU_agent 历史存储的 ORM 基类。"""


class AgentMessage(Base):
    """单条历史消息：thread_id 会话下按时间序排列的 user / assistant 记录。"""

    __tablename__ = "LBU_Agent_Message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class HistoryStore:
    """持有全局 async engine / session 工厂，提供历史记录的增查删。"""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._factory: async_sessionmaker | None = None

    @property
    def factory(self) -> async_sessionmaker:
        if self._factory is None:
            raise RuntimeError(
                "历史存储未初始化：请先 await storage.setup()（服务启动时自动执行）"
            )
        return self._factory

    async def setup(self) -> None:
        """建立 MySQL 连接并建表（幂等）。"""
        if self._engine is not None:
            return
        settings = get_settings()
        engine = create_async_engine(
            settings.mysql_dsn,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._engine = engine
        self._factory = async_sessionmaker(engine, expire_on_commit=False)

    async def save_exchange(self, thread_id: str, user_msg: str, reply: str) -> None:
        """一次问答写入两条记录（user + assistant），单事务提交。"""
        async with self.factory() as session:
            session.add_all(
                [
                    AgentMessage(thread_id=thread_id, role="user", content=user_msg),
                    AgentMessage(thread_id=thread_id, role="assistant", content=reply),
                ]
            )
            await session.commit()

    async def list_history(self, thread_id: str) -> list[AgentMessage]:
        """查询指定会话的历史记录，按 id 正序（即时间正序，供前端展示）。"""
        async with self.factory() as session:
            result = await session.execute(
                select(AgentMessage)
                .where(AgentMessage.thread_id == thread_id)
                .order_by(AgentMessage.id)
            )
            return list(result.scalars())

    async def clear(self, thread_id: str) -> None:
        """删除指定会话的全部历史记录（幂等）。"""
        async with self.factory() as session:
            await session.execute(
                delete(AgentMessage).where(AgentMessage.thread_id == thread_id)
            )
            await session.commit()


storage = HistoryStore()
