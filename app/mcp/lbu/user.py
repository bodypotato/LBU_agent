"""用户资料工具。"""

from app.mcp.lbu.api import call_lbu


def user_get_info(thread_id: str) -> str:
    """查看当前用户自己的资料（账号、昵称、注册时间）。"""
    return call_lbu(thread_id, "GET", "/api/user/info")


def user_update_name(name: str, thread_id: str) -> str:
    """修改当前用户自己的昵称。

    name 是新昵称（1-50 个字符）。
    """
    return call_lbu(thread_id, "PUT", "/api/user/name", json_body={"name": name})
