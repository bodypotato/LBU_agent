"""消息工具：发消息（STOMP WebSocket）、聊天记录、会话列表、已读/删除。

后端没有发消息的 REST 端点，发送走 STOMP 通道（/ws?token=xxx，
Spring 的 AuthHandshakeInterceptor 校验 token，支持多端同时在线）。
这里用 websockets 库实现最小 STOMP 客户端：CONNECT → SEND → 等回执。
"""

import asyncio
import json

import websockets

from app.config import get_settings
from app.mcp.lbu.api import call_lbu, get_token


async def _stomp_send(thread_id: str, destination: str, body: dict) -> str:
    """以用户身份连接后端 WS，发送一条 STOMP 消息并等待回执。"""
    token = get_token(thread_id)
    if not token:
        return (
            "操作失败：没有获取到用户的登录凭证。"
            "请告知用户先登录 LBU 后再试一次。"
        )
    settings = get_settings()
    ws_url = (
        settings.lbu_backend_base_url.replace("http://", "ws://", 1).rstrip("/")
        + f"/ws?token={token}"
    )
    try:
        async with websockets.connect(ws_url, open_timeout=5.0) as ws:
            await ws.send("CONNECT\naccept-version:1.2\nhost:localhost\n\n\x00")
            frame = await asyncio.wait_for(ws.recv(), timeout=5.0)
            if not frame.startswith("CONNECTED"):
                return f"操作失败：消息服务连接失败（{frame[:100]}）。请告知用户稍后再试。"
            await ws.send(
                f"SEND\ndestination:{destination}\n"
                f"content-type:application/json\nreceipt:lbu-agent\n\n"
                f"{json.dumps(body, ensure_ascii=False)}\x00"
            )
            try:
                while True:  # 等 RECEIPT / ERROR，最多 3 秒
                    frame = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    if frame.startswith("RECEIPT"):
                        return "消息已发送成功。"
                    if frame.startswith("ERROR"):
                        return f"操作失败：消息被拒绝（{frame[:200]}）。"
            except asyncio.TimeoutError:
                return "消息已发送。"
    except Exception as e:  # noqa: BLE001 —— 网络异常统一转提示
        return f"操作失败：消息发送出错（{e}）。请告知用户稍后再试。"


async def message_send_private(to_account: str, content: str, thread_id: str = "") -> str:
    """给指定好友发送私聊消息。

    to_account 是对方账号，content 是消息内容（不超过 5000 字）。
    发给普通用户要求双方已是好友；发给 ai_bot 不需要好友关系。
    """
    return await _stomp_send(
        thread_id, "/app/chat.private",
        {"toAccount": to_account, "content": content},
    )


async def message_send_group(group_id: int, content: str, thread_id: str = "") -> str:
    """往一个群里发消息。

    group_id 是群编号（从 group_list 返回里取），content 是消息内容
    （不超过 5000 字）；被禁言时发送会被拒绝。
    """
    return await _stomp_send(
        thread_id, "/app/chat.group",
        {"groupId": group_id, "content": content},
    )


def message_chat_history(other_account: str, page: int = 0, thread_id: str = "") -> str:
    """查看与某个好友的聊天记录（按时间正序，最新的一页在 page=0）。

    other_account 是对方账号，page 是页码（从 0 开始，每页 50 条，往前翻页时增大）。
    """
    return call_lbu(
        thread_id, "GET", f"/api/message/chat/{other_account}",
        params={"page": page, "size": 50},
    )


def message_conversations(thread_id: str) -> str:
    """查看我的单聊会话列表（各会话的最后一条消息与未读数）。"""
    return call_lbu(thread_id, "GET", "/api/message/conversations")


def message_offline(thread_id: str) -> str:
    """拉取我未收到的离线消息（拉取后会被标记为已送达）。"""
    return call_lbu(thread_id, "GET", "/api/message/offline")


def message_mark_read(from_account: str, thread_id: str) -> str:
    """把某个好友发来的消息标记为已读。

    from_account 是对方账号。
    """
    return call_lbu(thread_id, "PUT", f"/api/message/read/{from_account}")


def message_delete(message_id: int, thread_id: str) -> str:
    """删除一条私聊消息（仅自己不可见，执行前先向用户确认）。

    message_id 是消息编号（从 message_chat_history 返回里取）。
    """
    return call_lbu(thread_id, "PUT", f"/api/message/{message_id}/delete")
