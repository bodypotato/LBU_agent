"""会话记忆：以 thread_id 为粒度的对话上下文管理，持久化到 Redis。

- checkpointer 使用 AsyncRedisSaver（langgraph-checkpoint-redis），会话历史落盘，
  服务重启后上下文不丢。Redis 连接参数（REDIS_URL / REDIS_PASSWORD）在 .env 中。
- 与 LinkBetweenUs 后端共用 Redis 实例，key 均带 checkpoint 前缀，互不干扰。
- thread_id 对应「用户 account × ai_bot」的独立对话，同一用户连续对话传同一个
  thread_id 即延续上下文。
- clear(thread_id) 支持按会话清空上下文。
- compact(thread_id) 每次对话后把 checkpoint 压缩为每会话一条（覆盖式）。

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

    async def compact(self, thread_id: str) -> None:
        """压缩会话 checkpoint：每个 namespace 只保留最新一条（覆盖式，非 TTL）。

        LangGraph 每个 superstep 都会追加一个 checkpoint（版本回溯用），长期只增不减。
        而每个 checkpoint 内联存储了该会话的完整消息历史（channel_values），
        因此只留最新一条不丢上下文，仅丢弃 time travel 能力——用官方 aprune
        的 keep_latest 策略实现覆盖语义，避免 TTL 方案"最新一条也过期丢上下文"的问题。
        """
        await self.checkpointer.aprune([thread_id], strategy="keep_latest")

    async def rollback(self, thread_id: str, started_at_ms: float) -> None:
        """回滚一次失败的对话请求：删除本次 run 写入的 checkpoint，并把
        checkpoint_latest 指针滚回请求前的最新一条。

        LangGraph 在 run 开始就会写 input checkpoint（用户消息已入 state），
        模型调用失败时不会自行清理；不处理的话，重试会在 state 里累积重复的
        用户消息，持续污染后续请求的上下文。chat 失败分支调用本方法。

        判定依据：checkpoint_ts（毫秒）>= 请求开始时间即视为本次 run 产生。
        说明：AsyncRedisSaver 未提供按 checkpoint 删除 / 指针回退的公开 API，
        这里通过其底层 Redis 客户端与 key 构造器直接操作（uv.lock 锁定版本），
        扫描模式全部来自库自身的构造方法，不硬编码存储格式。
        """
        saver = self.checkpointer
        client = saver._redis  # noqa: SLF001 —— 库未暴露公开 API，只能走底层客户端
        sep = saver._separator

        # 1. 枚举本线程全部 checkpoint 文档（root namespace），按写入时间分类
        ckpt_pattern = saver._make_redis_checkpoint_key_cached(thread_id, "", "*")
        evicted: dict[str, str] = {}  # 本次 run 产生的 checkpoint_id -> key
        kept: list[tuple[float, str]] = []  # 请求前已有的 (checkpoint_ts, key)
        async for raw in client.scan_iter(match=ckpt_pattern):
            key = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
            try:
                doc = await client.json().get(key)
            except Exception:  # noqa: BLE001 —— 单 key 读取失败跳过，不影响其余
                continue
            if not isinstance(doc, dict):
                continue
            ts = float(doc.get("checkpoint_ts") or 0.0)
            if ts >= started_at_ms:
                evicted[doc.get("checkpoint_id") or ""] = key
            else:
                kept.append((ts, key))

        if not evicted:
            return

        # 2. 删除本次 run 的 checkpoint 文档及其 writes / zset 附属 key
        for key in evicted.values():
            await client.delete(key)
        writes_pattern = saver._make_redis_checkpoint_writes_key_cached(
            thread_id, "", "*", "*", "*"
        )
        async for raw in client.scan_iter(match=writes_pattern):
            key = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
            if any(seg in evicted for seg in key.split(sep)):
                await client.delete(key)
        for cid in evicted:
            await client.delete(
                saver._key_registry.make_write_keys_zset_key(thread_id, "", cid)
            )

        # 3. 重设 latest 指针：有剩余则指向请求前的最新一条；没有剩余则删除指针，
        #    该会话回到"无历史"状态，下次请求从全新对话开始
        pointer_key = saver._make_redis_checkpoint_latest_key(thread_id, "")
        if kept:
            await client.set(pointer_key, max(kept, key=lambda t: t[0])[1])
        else:
            await client.delete(pointer_key)

    def config_for(self, thread_id: str | None) -> RunnableConfig:
        """构造 invoke 使用的 config，thread_id 为空时使用默认会话。"""
        return {"configurable": {"thread_id": thread_id or DEFAULT_THREAD_ID}}


memory = ConversationMemory()
