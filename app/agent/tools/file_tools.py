"""文件读写工具：在 agent 专属工作区（AGENT_WORKSPACE_DIR）内读写文件。

安全约定：
- 所有路径都相对工作区根目录解析，越出工作区的路径（绝对路径、.. 跳级等）
  一律拒绝，防止 agent 误读写项目源码、系统文件或用户敏感文件；
- read_file 单次读取有字符上限（FILE_MAX_READ_CHARS），超出部分截断并明确
  提示，避免大文件内容撑爆对话上下文。
"""

from pathlib import Path

from langchain_core.tools import tool

from app.config import get_settings


def _workspace_root() -> Path:
    """工作区根目录（相对路径按进程工作目录解析，与 RAG 目录约定一致）。"""
    return Path(get_settings().agent_workspace_dir).resolve()


def _resolve_in_workspace(path: str) -> Path:
    """把工具传入的路径解析到工作区内；越出工作区时抛 ValueError。

    先拼在工作区根目录下再 resolve，配合 is_relative_to 校验，
    绝对路径 / .. / 盘符等写法都会被挡在工作区外。
    """
    root = _workspace_root()
    candidate = (root / path).resolve() if path.strip() else root
    if not candidate.is_relative_to(root):
        raise ValueError(f"路径超出工作区范围：{path}")
    return candidate


@tool
def list_files(path: str = "") -> str:
    """列出工作区中指定目录的内容。

    path 是相对于工作区根目录的路径，留空则列出根目录；
    返回目录与文件清单（目录在前），可据此决定下一步读取哪个文件。
    """
    try:
        target = _resolve_in_workspace(path)
    except ValueError as e:
        return f"无法访问该路径：{e}"
    if not target.exists():
        return f"目录不存在：{path or '工作区根目录'}（工作区还是空的，可用 write_file 创建文件）"
    if not target.is_dir():
        return f"{path} 不是目录，请用 read_file 读取文件内容。"
    try:
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as e:
        return f"列目录失败：{e}"
    if not entries:
        return f"目录 {path or '工作区根目录'} 为空。"
    lines = []
    for p in entries:
        kind = "目录" if p.is_dir() else "文件"
        detail = "" if p.is_dir() else f"，{p.stat().st_size} 字节"
        lines.append(f"- {p.name}（{kind}{detail}）")
    return f"目录 {path or '工作区根目录'} 的内容：\n" + "\n".join(lines)


@tool
def read_file(path: str) -> str:
    """读取工作区中指定文本文件的内容。

    path 是相对于工作区根目录的路径；单次最多返回前 FILE_MAX_READ_CHARS
    字符，超出时截断并在结尾提示，可分多次续读。
    """
    try:
        target = _resolve_in_workspace(path)
    except ValueError as e:
        return f"无法读取：{e}"
    if not target.exists():
        return f"文件不存在：{path}"
    if target.is_dir():
        return f"{path} 是目录，请用 list_files 查看其中的内容。"
    limit = get_settings().file_max_read_chars
    try:
        with target.open(encoding="utf-8", errors="replace") as f:
            text = f.read(limit + 1)
    except OSError as e:
        return f"读取失败：{e}"
    truncated = len(text) > limit
    if truncated:
        text = text[:limit]
    head = f"文件 {target} 的内容：\n\n{text}"
    if truncated:
        head += f"\n\n……（内容过长，以上为前 {limit} 字符；如继续需要可告知我分次读取）"
    return head


@tool
def write_file(path: str, content: str) -> str:
    """把内容写入工作区中的文件（文件已存在则覆盖，父目录不存在会自动创建）。

    path 是相对于工作区根目录的路径，content 是完整文件内容。
    适合生成报告、记录笔记、保存用户提供的数据等场景。
    """
    try:
        target = _resolve_in_workspace(path)
    except ValueError as e:
        return f"无法写入：{e}"
    if target.is_dir():
        return f"{path} 是已存在的目录，请换一个文件名。"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"写入失败：{e}"
    return f"已写入文件：{target}（{len(content)} 字符）"


@tool
def append_file(path: str, content: str) -> str:
    """在文件末尾追加内容（文件不存在则自动创建）。

    path 是相对于工作区根目录的路径，content 是要追加的内容。
    适合给已有文件补充内容，不需要重写全文。
    """
    try:
        target = _resolve_in_workspace(path)
    except ValueError as e:
        return f"无法追加：{e}"
    if target.is_dir():
        return f"{path} 是已存在的目录，请换一个文件名。"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return f"追加失败：{e}"
    return f"已追加到文件：{target}（本次追加 {len(content)} 字符）"


FILE_TOOLS: list = [
    list_files,
    read_file,
    write_file,
    append_file,
]
