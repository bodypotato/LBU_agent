"""工具包：统一注册入口（内置工具 + MCP 工具）。

内置工具（agent 进程内）：
- builtin.py：search_lbu_docs（RAG 依赖 Chroma/embedding，留在 agent 进程）
- skill_tools.py：load_skill（技能加载，与 agent 配置/提示词耦合）

通用能力工具（文件/时间/后端健康/联网）已迁入 lbu-tools MCP 服务
（app/mcp/server.py，独立进程，streamable HTTP），经 app/agent/mcp_client.py
异步加载。后续 LBU 业务工具（好友/聊天/群组等）也走 MCP 接入，本包不再
逐个新增工具模块。
"""

from app.agent.mcp_client import load_mcp_tools
from app.agent.tools.builtin import BUILTIN_TOOLS
from app.agent.tools.skill_tools import SKILL_TOOLS

# 进程内工具清单（MCP 工具在 get_tools 时动态加载）。
BUILTIN_TOOLS: list = [*BUILTIN_TOOLS, *SKILL_TOOLS]


async def get_tools() -> list:
    """返回注册给 agent 的全部工具（内置 + MCP）。"""
    return [*BUILTIN_TOOLS, *await load_mcp_tools()]


__all__ = ["get_tools"]
