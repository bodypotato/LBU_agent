"""技能加载工具：渐进披露（描述常驻 system prompt，正文按需加载）。"""

from langchain_core.tools import tool

from app.agent.skills import get_skill, list_skills
from app.config import get_settings


def _available_text() -> str:
    skills = list_skills()
    if not skills:
        return "当前没有任何已安装的技能。"
    return "当前可用技能：" + "、".join(
        f"{s.name}（{s.description}）" for s in skills
    )


@tool
def load_skill(skill_name: str, resource: str = "") -> str:
    """加载指定技能的完整说明，或技能目录下的资源文件。

    skill_name 是技能名称（可用技能见系统提示中的清单），resource 留空则
    返回技能说明正文；技能说明中提到的资源文件需要读内容时，再调用本工具
    并填写 resource 文件名。加载后必须严格遵循技能说明的步骤完成用户任务。
    """
    skill = get_skill(skill_name)
    if skill is None:
        return f"没有找到技能「{skill_name}」。{_available_text()}"
    if not resource:
        head = (
            f"技能「{skill.display_name}」的说明如下，请严格按其中的步骤执行：\n\n"
            f"{skill.body}"
        )
        if skill.resources:
            names = "、".join(skill.resources)
            head += (
                f"\n\n本技能目录下还有资源文件：{names}"
                f"（需要读某个文件的内容时，再次调用本工具并填写 resource）"
            )
        return head
    # 资源文件只能读技能目录内的文件，越界一律拒绝
    target = (skill.path / resource).resolve()
    if not target.is_relative_to(skill.path.resolve()):
        return f"资源文件超出技能目录范围，已拒绝：{resource}"
    if not target.is_file():
        return (
            f"资源文件不存在：{resource}。技能目录下的资源文件有："
            + "、".join(skill.resources)
            + ("。" if skill.resources else "（无）。")
        )
    limit = get_settings().file_max_read_chars
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"读取资源文件失败：{e}"
    if len(text) > limit:
        text = text[:limit] + f"\n\n……（内容过长，以上为前 {limit} 字符，可换更小的资源文件）"
    return f"技能「{skill.display_name}」的资源文件 {resource} 的内容：\n\n{text}"


SKILL_TOOLS: list = [load_skill]
