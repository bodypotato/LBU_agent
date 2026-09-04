"""用户凭证上下文：按 thread_id 暂存 LinkBetweenUs 用户的 JWT。

agent 代替用户操作后端（好友/群组/资料/消息）需要用户本人的 token。
由于后端"登录即顶号"（每次登录使旧 token 失效，JwtUtil 版本号机制），
agent 不能替用户登录，token 必须由调用方（客户端/后端接入层）随 chat
请求携带过来，本模块按 thread_id 暂存到 Redis，供 MCP 业务工具取用。

key 前缀 lbu:agent:token:，与 checkpoint、后端其他 key 互不干扰；
TTL 48 小时（后端 token 本身 24 小时过期，多留一倍余量）。
"""

import redis.asyncio as aioredis

from app.config import get_settings

TOKEN_KEY_PREFIX = "lbu:agent:token:"
TOKEN_TTL_SECONDS = 48 * 3600

_client: aioredis.Redis | None = None


def _redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            get_settings().redis_dsn, decode_responses=True
        )
    return _client


async def set_token(thread_id: str, token: str) -> None:
    """暂存会话对应的用户 token（覆盖旧值）。失败只记日志不影响对话。"""
    try:
        await _redis().set(
            f"{TOKEN_KEY_PREFIX}{thread_id}", token, ex=TOKEN_TTL_SECONDS
        )
    except Exception:  # noqa: BLE001 —— Redis 异常降级
        pass


async def delete_token(thread_id: str) -> None:
    """清空会话对应的用户 token（清会话时调用）。"""
    try:
        await _redis().delete(f"{TOKEN_KEY_PREFIX}{thread_id}")
    except Exception:  # noqa: BLE001
        pass
