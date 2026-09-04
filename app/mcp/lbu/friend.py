"""好友工具：搜索、申请、处理申请、好友管理。"""

from app.mcp.lbu.api import call_lbu


def friend_search(keyword: str, thread_id: str) -> str:
    """按账号或昵称模糊搜索 LBU 用户（加好友前先用它找到对方账号）。

    keyword 是搜索关键词，返回最多 20 个匹配用户（含账号 account 和昵称 name）。
    """
    return call_lbu(thread_id, "GET", "/api/friend/search", params={"keyword": keyword})


def friend_request_send(to_account: str, message: str = "", thread_id: str = "") -> str:
    """向指定账号发送好友申请。

    to_account 是对方账号（不确定时先用 friend_search 搜索），
    message 是附言（可选，不超过 255 字）。
    """
    body = {"toAccount": to_account}
    if message:
        body["message"] = message
    return call_lbu(thread_id, "POST", "/api/friend/request", json_body=body)


def friend_request_incoming(thread_id: str) -> str:
    """查看别人发给我的好友申请列表（未处理的和已处理的）。"""
    return call_lbu(thread_id, "GET", "/api/friend/request/incoming")


def friend_request_outgoing(thread_id: str) -> str:
    """查看我发出去的好友申请列表。"""
    return call_lbu(thread_id, "GET", "/api/friend/request/outgoing")


def friend_request_accept(request_id: int, thread_id: str) -> str:
    """同意一条好友申请（对方就正式成为好友）。

    request_id 是申请编号，从 friend_request_incoming 的返回数据里取。
    """
    return call_lbu(thread_id, "PUT", f"/api/friend/request/{request_id}/accept")


def friend_request_reject(request_id: int, thread_id: str) -> str:
    """拒绝一条好友申请。

    request_id 是申请编号，从 friend_request_incoming 的返回数据里取。
    """
    return call_lbu(thread_id, "PUT", f"/api/friend/request/{request_id}/reject")


def friend_list(thread_id: str) -> str:
    """查看我的好友列表（账号、昵称、备注）。"""
    return call_lbu(thread_id, "GET", "/api/friend")


def friend_delete(friend_account: str, thread_id: str) -> str:
    """删除一个好友（双方好友关系解除，不可恢复，执行前先向用户确认）。

    friend_account 是对方的账号。
    """
    return call_lbu(thread_id, "DELETE", f"/api/friend/{friend_account}")


def friend_set_remark(friend_account: str, remark: str, thread_id: str) -> str:
    """给某个好友设置或修改备注名（传空字符串表示清除备注）。

    friend_account 是对方的账号，remark 是备注内容（不超过 32 字）。
    """
    return call_lbu(
        thread_id, "PUT", f"/api/friend/{friend_account}/remark",
        json_body={"remark": remark},
    )
