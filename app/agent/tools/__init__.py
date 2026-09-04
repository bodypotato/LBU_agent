"""工具包：统一注册入口。

内置工具（builtin.py）：
- get_current_time            通用时间查询
- check_lbu_backend_health   探测 LinkBetweenUs 后端是否在线
- search_lbu_docs            RAG 检索 LBU 产品文档（docs/LBU.md，父子文档模式）

文件工具（file_tools.py）：
- list_files / read_file / write_file / append_file
                              工作区内文件读写（AGENT_WORKSPACE_DIR 沙箱）

技能工具（skill_tools.py）：
- load_skill                  加载技能说明正文/资源文件（渐进披露，SKILLS_DIR）

后续按需在本包下按模块扩展 LBU 业务工具
（friend / chat / group / online / user ...），扩展后在 BUILTIN_TOOLS 统一注册。
"""

from app.agent.tools.builtin import BUILTIN_TOOLS
from app.agent.tools.file_tools import FILE_TOOLS
from app.agent.tools.skill_tools import SKILL_TOOLS

# create_agent 的 tools 参数从这里取，后续新增工具只需加入 BUILTIN_TOOLS。
BUILTIN_TOOLS: list = [*BUILTIN_TOOLS, *FILE_TOOLS, *SKILL_TOOLS]


def get_tools() -> list:
    """返回注册给 agent 的全部工具。"""
    return list(BUILTIN_TOOLS)


__all__ = ["BUILTIN_TOOLS", "get_tools"]
