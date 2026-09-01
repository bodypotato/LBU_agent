"""工具注册。

地基阶段内置两个基础工具：
- get_current_time            通用时间查询
- check_lbu_backend_health   探测 LinkBetweenUs 后端是否在线

后续按需在 app/agent/tools/ 下按模块扩展 LBU 业务工具
（friend / chat / group / online / user ...），扩展后在此统一注册。
"""

from datetime import datetime

import httpx
from langchain_core.tools import tool

from app.config import get_settings

# ===== 内置工具 =====


@tool
def get_current_time() -> str:
    """获取当前日期和时间（北京时区为 UTC+8，返回 ISO 格式，不含时区换算）。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


@tool
def check_lbu_backend_health() -> str:
    """探测 LinkBetweenUs 后端服务是否在线可达。

    返回后端地址及连通状态，供回答"服务是否正常"类问题时使用。
    """
    settings = get_settings()
    base = settings.lbu_backend_base_url.rstrip("/")
    try:
        resp = httpx.get(f"{base}/error", timeout=3.0)
        # /error 是后端白名单路径，无 JWT 也可访问，连通即代表服务在线
        return f"LinkBetweenUs 后端（{base}）在线，HTTP 状态码 {resp.status_code}。"
    except httpx.HTTPError:
        return f"LinkBetweenUs 后端（{base}）当前不可达，服务可能未启动。"


# ===== 统一注册入口 =====
# create_agent 的 tools 参数从这里取，后续新增工具只需加入 BUILTIN_TOOLS。

BUILTIN_TOOLS: list = [
    get_current_time,
    check_lbu_backend_health,
]


def get_tools() -> list:
    """返回注册给 agent 的全部工具。"""
    return list(BUILTIN_TOOLS)
