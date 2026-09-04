"""LBU 业务工具公共层：后端 REST 调用 + 凭证获取 + Result 统一解析。

身份约定：调用方随 chat 请求把用户 JWT 传给 LBU_agent（body 或
Authorization 头），agent 按 thread_id 暂存到 Redis（key 与 auth_context
一致）；业务工具声明 thread_id 参数，由 agent 侧拦截器注入真实值，
这里按 thread_id 取 token 调后端——token 不进模型上下文。
"""

import json
import logging
from typing import Any

import httpx
from redis import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)

TOKEN_KEY_PREFIX = "lbu:agent:token:"

_redis: Redis | None = None


def _redis_client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_dsn, decode_responses=True)
    return _redis


def get_token(thread_id: str) -> str | None:
    """按 thread_id 取暂存的用户 JWT（Redis 不可用时返回 None）。"""
    try:
        return _redis_client().get(f"{TOKEN_KEY_PREFIX}{thread_id}")
    except Exception as e:  # noqa: BLE001 —— 凭证读取失败按未登录处理
        logger.warning("读取用户凭证失败: %s", e)
        return None


def _backend_base() -> str:
    return get_settings().lbu_backend_base_url.rstrip("/")


def call_lbu(
    thread_id: str,
    method: str,
    path: str,
    params: dict | None = None,
    json_body: dict | None = None,
) -> str:
    """调用 LinkBetweenUs 后端 REST 接口，统一解析 Result 并返回给模型的中文文本。

    返回的永远是给模型看的字符串（业务工具直接透传）：
    - 无凭证 → 提示用户未登录；
    - HTTP 401 → 提示登录过期（后端 token 24 小时有效且登录即顶号）；
    - Result.code != 200 → 后端 message；
    - 成功 → "操作成功" 或 data 的 JSON 文本。
    """
    token = get_token(thread_id)
    if not token:
        return (
            "操作失败：没有获取到用户的登录凭证。"
            "请告知用户先登录 LBU 后再试一次。"
        )
    try:
        resp = httpx.request(
            method,
            f"{_backend_base()}{path}",
            params=params,
            json=json_body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
    except httpx.HTTPError as e:
        return f"操作失败：无法连接 LinkBetweenUs 后端（{e}）。请告知用户稍后再试。"
    if resp.status_code == 401:
        return "操作失败：登录已过期。请告知用户重新登录 LBU 后再试。"
    try:
        payload: dict[str, Any] = resp.json()
    except ValueError:
        return f"操作失败：后端返回了无法解析的响应（HTTP {resp.status_code}）。"
    code = payload.get("code")
    message = str(payload.get("message") or "")
    data = payload.get("data")
    if code != 200:
        return f"操作失败：{message or f'后端返回错误码 {code}'}"
    if data is None:
        return "操作成功。"
    return "操作成功，返回数据：\n" + json.dumps(data, ensure_ascii=False)
