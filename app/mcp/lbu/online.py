"""在线状态工具。"""

from app.mcp.lbu.api import call_lbu


def online_list(thread_id: str) -> str:
    """查看当前所有在线用户的账号列表。"""
    return call_lbu(thread_id, "GET", "/api/online")


def online_is_online(account: str, thread_id: str) -> str:
    """查看某个用户当前是否在线。

    account 是对方的账号。
    """
    return call_lbu(thread_id, "GET", f"/api/online/{account}")
