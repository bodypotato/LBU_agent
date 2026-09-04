"""LBU 业务工具：代替用户操作 LinkBetweenUs 后端（资料/好友/群组/消息/在线）。

身份约定（详见 api.py）：调用方随 chat 请求携带用户 JWT，agent 按
thread_id 暂存到 Redis；工具声明 thread_id 参数，由 agent 侧拦截器
（app/agent/mcp_client.py 的 ThreadIdInjector）注入真实值——模型无法
伪造身份，token 不进入模型上下文。
"""

from mcp.server.fastmcp import FastMCP

from app.mcp.lbu import friend, group, message, online, user

# 全部业务工具（新工具在此追加，注册到 MCP 后 agent 侧零改动自动获得）。
LBU_TOOLS: list = [
    # 用户资料
    user.user_get_info,
    user.user_update_name,
    # 好友
    friend.friend_search,
    friend.friend_request_send,
    friend.friend_request_incoming,
    friend.friend_request_outgoing,
    friend.friend_request_accept,
    friend.friend_request_reject,
    friend.friend_list,
    friend.friend_delete,
    friend.friend_set_remark,
    # 群组
    group.group_create,
    group.group_list,
    group.group_get_info,
    group.group_delete,
    group.group_rename,
    group.group_members,
    group.group_kick,
    group.group_promote,
    group.group_demote,
    group.group_mute,
    group.group_unmute,
    group.group_leave,
    group.group_join,
    group.group_join_pending,
    group.group_join_approve,
    group.group_join_reject,
    group.group_messages,
    group.group_conversations,
    group.group_mark_read,
    group.group_delete_message,
    # 消息
    message.message_send_private,
    message.message_send_group,
    message.message_chat_history,
    message.message_conversations,
    message.message_offline,
    message.message_mark_read,
    message.message_delete,
    # 在线状态
    online.online_list,
    online.online_is_online,
]


def register_lbu_tools(mcp: FastMCP) -> None:
    """把全部 LBU 业务工具挂到 MCP 实例上。"""
    for tool in LBU_TOOLS:
        mcp.tool()(tool)
