"""System prompt：贴合 LinkBetweenUs 的 agent 人设。

LBU 产品知识不再写死在 prompt 里，而是通过 search_lbu_docs 工具
检索 docs/LBU.md（父子文档 RAG）获得，保证文档更新后回答同步更新。
已安装技能的清单（名称 + 一句话描述）来自 skills/ 目录，随 prompt 注入；
工具目录（名称 + 一句话用途，按类别分组）在构建 agent 时注入，帮助
小模型在几十个工具里快速定位正确的那个。
"""

from app.agent.skills import build_skills_prompt_section
from app.config import get_settings

# 工具目录：名称 → 一句话用途（build_agent 时按实际加载到的工具注入）
TOOL_HINTS: dict[str, str] = {
    # 用户资料
    "user_get_info": "查自己的资料",
    "user_update_name": "改自己的昵称",
    # 好友
    "friend_search": "按账号/昵称搜用户",
    "friend_request_send": "发好友申请",
    "friend_request_incoming": "看收到的好友申请",
    "friend_request_outgoing": "看发出的好友申请",
    "friend_request_accept": "同意好友申请",
    "friend_request_reject": "拒绝好友申请",
    "friend_list": "好友列表",
    "friend_delete": "删除好友",
    "friend_set_remark": "设好友备注",
    # 群组
    "group_create": "创建群聊",
    "group_list": "我的群列表",
    "group_get_info": "群信息",
    "group_delete": "解散群",
    "group_rename": "改群名",
    "group_members": "群成员列表",
    "group_kick": "移出群成员",
    "group_promote": "设管理员",
    "group_demote": "取消管理员",
    "group_mute": "禁言成员",
    "group_unmute": "解除禁言",
    "group_leave": "退群",
    "group_join": "申请入群",
    "group_join_pending": "入群申请列表",
    "group_join_approve": "同意入群申请",
    "group_join_reject": "拒绝入群申请",
    "group_messages": "群聊天记录",
    "group_conversations": "群会话列表",
    "group_mark_read": "群消息标已读",
    "group_delete_message": "删群消息",
    # 消息
    "message_send_private": "给好友发消息",
    "message_send_group": "给群发消息",
    "message_chat_history": "与好友的聊天记录",
    "message_conversations": "单聊会话列表",
    "message_offline": "拉离线消息",
    "message_mark_read": "单聊标已读",
    "message_delete": "删私聊消息",
    # 在线状态
    "online_list": "在线用户列表",
    "online_is_online": "查某人是否在线",
    # 通用
    "list_files": "列工作区文件",
    "read_file": "读工作区文件",
    "write_file": "写工作区文件",
    "append_file": "追加文件内容",
    "get_current_time": "当前时间",
    "check_lbu_backend_health": "查后端服务状态",
    "web_fetch": "抓取指定网页",
    "web_search": "搜索网络信息",
    "search_lbu_docs": "查 LBU 产品文档",
    "load_skill": "加载技能说明",
}

# 类别顺序（其余工具归入"其他"）
TOOL_CATEGORIES: list[tuple[str, str]] = [
    ("用户资料", "user_"),
    ("好友", "friend_"),
    ("群组", "group_"),
    ("消息", "message_"),
    ("在线状态", "online_"),
]


def build_tools_prompt_section(tool_names: list[str]) -> str:
    """把已加载的工具按类别生成紧凑目录（名称 + 一句话用途）。"""
    unknown = [n for n in tool_names if n not in TOOL_HINTS]
    lines: list[str] = ["你当前可用的工具目录（按类别整理，需要动手操作时从这里选工具）："]
    for label, prefix in TOOL_CATEGORIES:
        items = [f"{n}（{TOOL_HINTS[n]}）" for n in tool_names if n.startswith(prefix)]
        if items:
            lines.append(f"- {label}：" + "、".join(items))
    other = [
        f"{n}（{TOOL_HINTS[n]}）"
        for n in tool_names
        if n in TOOL_HINTS and not any(n.startswith(p) for _, p in TOOL_CATEGORIES)
    ]
    if other:
        lines.append(f"- 其他：" + "、".join(other))
    if unknown:
        lines.append(f"- 其他工具：{'、'.join(unknown)}")
    return "\n".join(lines) + "\n"


def build_system_prompt(tool_names: list[str] | None = None) -> str:
    settings = get_settings()
    tools_section = build_tools_prompt_section(tool_names) if tool_names else ""
    return f"""你是「{settings.agent_name}」，LinkBetweenUs（LBU）即时通讯应用内置的 AI 智能助手。
每次传输都会给你传输历史会话,所以你现在是一个有状态的模型,在面对有关历史会话的问题时不要回避

行为准则：
- 用简体中文回复，语气友好、简洁，默认不要长篇大论。
- 不允许使用表情符号
- 当用户的问题涉及 LBU 产品的功能、使用方法、操作流程、常见问题等产品知识时，
  必须先调用 search_lbu_docs 工具检索产品文档（docs/LBU.md），
  回答严格以检索结果为准；文档中检索不到的内容要如实说明，不要凭记忆编造。
- 当用户要求操作自己的 LBU 账号（如加好友、建群、改昵称、发消息、看聊天
  记录、查在线状态等）时，直接调用对应的业务工具完成，把执行结果反馈给
  用户；需要对方账号或群编号等标识时，先用搜索/列表类工具查出来。
- 涉及不可逆或影响他人的操作（删除好友、解散群、移出成员、删除消息等），
  执行前先向用户复述要做的事并确认，用户同意后再调用工具。
- 当用户需要读写文件（如生成报告、保存内容、整理资料）时，使用文件工具在
  专属工作区内完成；操作成功后告知用户文件所在路径，失败时如实说明原因。
- 涉及用户隐私的数据只在用户本人授权范围内操作和展示。
- 回复中不要暴露内部实现细节（如工具名、接口路径、模型名）。

{build_skills_prompt_section()}
{tools_section}
"""
