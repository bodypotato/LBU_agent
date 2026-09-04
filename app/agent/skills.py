"""技能系统：扫描 skills/ 目录，把技能说明渐进披露给模型。

约定（对齐 Claude Code 的 SKILL.md 用法）：
- 每个技能一个目录：SKILLS_DIR/<技能名>/SKILL.md，技能名即目录名；
- SKILL.md 首部 YAML frontmatter 含 name / description（均为单行字符串），
  description 是决定「何时触发」的一句话，会注入 system prompt 常驻可见；
- frontmatter 之后的正文是给模型的完整指令，只在模型调用 load_skill 工具
  或用户用 /技能名 显式触发时才进入上下文（渐进披露，节省小模型上下文）；
- 技能正文应短小、中文、自然语言步骤，不要要求严格格式输出（qwen3:4b
  结构化输出不可靠）；正文可直接指挥 agent 使用已注册的工具；
- 技能目录下除 SKILL.md 外的文件视为资源文件，可通过 load_skill 的
  resource 参数按需读取。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """一个已安装的技能。"""

    name: str  # 目录名，唯一标识
    display_name: str  # frontmatter 的 name，默认同目录名
    description: str
    path: Path  # 技能目录
    body: str  # SKILL.md 正文（不含 frontmatter）
    resources: list[str] = field(default_factory=list)  # 目录下的资源文件名


def _skills_root() -> Path:
    """技能根目录（相对路径按进程工作目录解析，与 RAG 目录约定一致）。"""
    return Path(get_settings().skills_dir).resolve()


def _parse_skill_md(text: str) -> tuple[dict, str]:
    """拆出 frontmatter 与正文；无 frontmatter 时整篇当正文，宽松处理。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, parts[2].strip()


def list_skills() -> list[Skill]:
    """扫描技能根目录，返回全部技能（按名称排序）。

    每次调用实时扫描（目录很小，无缓存成本）：工具调用与斜杠触发能立即
    感知新增技能；system prompt 里的技能清单在 build_agent 时生成，需重启生效。
    """
    root = _skills_root()
    if not root.is_dir():
        return []
    skills: list[Skill] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8")
            meta, body = _parse_skill_md(text)
        except Exception as e:  # noqa: BLE001 —— 单个技能损坏不影响其他技能
            logger.warning("技能解析失败，已跳过: %s (%s)", skill_md, e)
            continue
        skill_dir = skill_md.parent
        dir_name = skill_dir.name
        skills.append(
            Skill(
                name=dir_name,
                display_name=str(meta.get("name") or dir_name),
                description=str(meta.get("description") or ""),
                path=skill_dir,
                body=body,
                resources=sorted(
                    p.name
                    for p in skill_dir.iterdir()
                    if p.is_file() and p.name != "SKILL.md"
                ),
            )
        )
    return skills


def get_skill(name: str) -> Skill | None:
    """按名称取技能：优先精确匹配目录名，其次匹配 frontmatter 的 name。"""
    if not name:
        return None
    for skill in list_skills():
        if name == skill.name or name == skill.display_name:
            return skill
    return None


def render_slash_message(raw: str) -> str:
    """把 /技能名 开头的用户消息渲染成带技能正文的提示词。

    不以 / 开头原样返回；/ 开头但技能不存在时，改写为「告知用户技能不存在
    并列出可用技能」的提示词，避免模型对着一个不存在的斜杠命令自由发挥。
    """
    msg = raw.strip()
    if not msg.startswith("/"):
        return raw
    name, _, user_input = msg[1:].partition(" ")
    skill = get_skill(name)
    if skill is None:
        available = "、".join(s.name for s in list_skills()) or "（当前暂无可用技能）"
        return (
            f"用户输入了 /{name}，但不存在这个技能。可用技能：{available}。"
            f"请告知用户该技能不存在，并列出可用技能供选择。"
        )
    user_line = f"\n\n用户的原话：{user_input.strip()}" if user_input.strip() else ""
    return (
        f"用户通过 /{name} 显式触发了技能「{skill.display_name}」，"
        f"请严格按以下技能说明执行：\n\n{skill.body}{user_line}"
    )


def build_skills_prompt_section() -> str:
    """生成注入 system prompt 的技能清单（渐进披露：只放名称与一句话描述）。"""
    skills = list_skills()
    if not skills:
        return ""
    lines = "\n".join(f"- {s.name}：{s.description}" for s in skills)
    return (
        "可用技能（当用户任务与某个技能描述相关时，先调用 load_skill 工具加载该技能说明，"
        "再按说明执行；用户也可以用 /技能名 直接触发）：\n"
        f"{lines}\n"
    )
