"""群组工具：建群、群管理、成员管理、入群审批、群消息查看。"""

from app.mcp.lbu.api import call_lbu


def group_create(name: str, members: list[str] | None = None, thread_id: str = "") -> str:
    """创建一个群聊，创建者自动成为群主。

    name 是群名称（1-100 字）；members 是初始成员账号列表（可选，不含自己，
    最多 50 个，这些人会被直接拉进群）。建群时不在 members 里的人需要
    通过"申请入群 → 审批"进入。
    """
    body: dict = {"name": name}
    if members:
        body["members"] = members
    return call_lbu(thread_id, "POST", "/api/group", json_body=body)


def group_list(thread_id: str) -> str:
    """查看我加入的所有群聊（群名、群主、成员数、创建时间）。"""
    return call_lbu(thread_id, "GET", "/api/group")


def group_get_info(group_id: int, thread_id: str) -> str:
    """查看某个群的基本信息。

    group_id 是群编号，从 group_list 的返回数据里取。
    """
    return call_lbu(thread_id, "GET", f"/api/group/{group_id}")


def group_delete(group_id: int, thread_id: str) -> str:
    """解散一个群（仅群主可操作，不可恢复，执行前先向用户确认）。

    group_id 是群编号。
    """
    return call_lbu(thread_id, "DELETE", f"/api/group/{group_id}")


def group_rename(group_id: int, name: str, thread_id: str) -> str:
    """修改群名称（群主或管理员可操作）。

    group_id 是群编号，name 是新群名（不超过 32 字）。
    """
    return call_lbu(thread_id, "PUT", f"/api/group/{group_id}/name", json_body={"name": name})


def group_members(group_id: int, thread_id: str) -> str:
    """查看群成员列表（账号、昵称、角色：0 群主 / 1 管理员 / 2 成员）。

    group_id 是群编号。
    """
    return call_lbu(thread_id, "GET", f"/api/group/{group_id}/members")


def group_kick(group_id: int, account: str, thread_id: str) -> str:
    """把某个成员移出群（群主或管理员可操作，执行前先向用户确认）。

    group_id 是群编号，account 是要移出的成员账号。
    """
    return call_lbu(thread_id, "PUT", f"/api/group/{group_id}/kick/{account}")


def group_promote(group_id: int, account: str, thread_id: str) -> str:
    """把某个成员设为管理员（仅群主可操作）。

    group_id 是群编号，account 是成员账号。
    """
    return call_lbu(thread_id, "PUT", f"/api/group/{group_id}/promote/{account}")


def group_demote(group_id: int, account: str, thread_id: str) -> str:
    """取消某个成员的管理员身份（仅群主可操作）。

    group_id 是群编号，account 是成员账号。
    """
    return call_lbu(thread_id, "PUT", f"/api/group/{group_id}/demote/{account}")


def group_mute(group_id: int, account: str, minutes: int, thread_id: str) -> str:
    """在群里禁言某个成员一段时间（群主或管理员可操作）。

    group_id 是群编号，account 是成员账号，minutes 是禁言时长（分钟，至少 1）。
    """
    return call_lbu(
        thread_id, "PUT", f"/api/group/{group_id}/mute/{account}",
        json_body={"minutes": minutes},
    )


def group_unmute(group_id: int, account: str, thread_id: str) -> str:
    """解除群里某个成员的禁言。

    group_id 是群编号，account 是成员账号。
    """
    return call_lbu(thread_id, "PUT", f"/api/group/{group_id}/unmute/{account}")


def group_leave(group_id: int, thread_id: str) -> str:
    """退出一个群（群主不能退群，需先解散或转让，执行前先向用户确认）。

    group_id 是群编号。
    """
    return call_lbu(thread_id, "PUT", f"/api/group/{group_id}/leave")


def group_join(group_id: int, message: str = "", thread_id: str = "") -> str:
    """申请加入一个群（提交后等待群主或管理员审批）。

    group_id 是群编号（从群列表或群信息里取），message 是申请附言（可选）。
    """
    body = {"message": message} if message else {}
    return call_lbu(thread_id, "POST", f"/api/group/{group_id}/join", json_body=body)


def group_join_pending(group_id: int, thread_id: str) -> str:
    """查看某个群的入群申请列表（群主或管理员可操作）。

    group_id 是群编号。
    """
    return call_lbu(thread_id, "GET", f"/api/group/{group_id}/join/pending")


def group_join_approve(group_id: int, request_id: int, thread_id: str) -> str:
    """同意一条入群申请。

    group_id 是群编号，request_id 是申请编号（从 group_join_pending 返回里取）。
    """
    return call_lbu(thread_id, "PUT", f"/api/group/{group_id}/join/{request_id}/approve")


def group_join_reject(group_id: int, request_id: int, thread_id: str) -> str:
    """拒绝一条入群申请。

    group_id 是群编号，request_id 是申请编号（从 group_join_pending 返回里取）。
    """
    return call_lbu(thread_id, "PUT", f"/api/group/{group_id}/join/{request_id}/reject")


def group_messages(group_id: int, page: int = 0, thread_id: str = "") -> str:
    """查看群聊天记录（按时间正序，最新的一页在 page=0）。

    group_id 是群编号，page 是页码（从 0 开始，每页 50 条，往前翻页时增大）。
    """
    return call_lbu(
        thread_id, "GET", f"/api/group/{group_id}/messages",
        params={"page": page, "size": 50},
    )


def group_conversations(thread_id: str) -> str:
    """查看我的群会话列表（各群的最后一条消息与未读数）。"""
    return call_lbu(thread_id, "GET", "/api/group/conversations")


def group_mark_read(group_id: int, thread_id: str) -> str:
    """把某个群的未读消息标记为已读。

    group_id 是群编号。
    """
    return call_lbu(thread_id, "PUT", f"/api/group/{group_id}/read")


def group_delete_message(group_id: int, message_id: int, thread_id: str) -> str:
    """删除群聊里的一条消息（仅自己不可见，执行前先向用户确认）。

    group_id 是群编号，message_id 是消息编号（从 group_messages 返回里取）。
    """
    return call_lbu(
        thread_id, "PUT", f"/api/group/{group_id}/message/{message_id}/delete"
    )
