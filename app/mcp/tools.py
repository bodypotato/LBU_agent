"""lbu-tools 的通用能力工具：文件（工作区沙箱）/ 时间 / 后端健康 / 网页抓取。

自 app/agent/tools 迁移而来，改挂 FastMCP；安全约定不变：
- 文件工具只读写 AGENT_WORKSPACE_DIR 工作区，越界路径（绝对路径、.. 跳级）
  一律拒绝，防止误读写项目源码、系统文件或用户敏感文件；
- read_file 单次读取有字符上限（FILE_MAX_READ_CHARS），超长截断提示；
- web_fetch 只抓 http(s) 文本页，转纯文本后按 WEB_MAX_FETCH_CHARS 截断。
"""

import re
from datetime import datetime
from html import unescape
from pathlib import Path

import html2text
import httpx
from mcp.server.fastmcp import FastMCP

from app.config import get_settings


# ===== 文件工具（工作区沙箱）=====


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


# ===== 时间 / 后端健康 =====


def get_current_time() -> str:
    """获取当前日期和时间（北京时区为 UTC+8，返回 ISO 格式，不含时区换算）。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def check_lbu_backend_health() -> str:
    """探测 LinkBetweenUs 后端服务是否在线可达。

    返回后端地址及连通状态，供回答"服务是否正常"类问题时使用。
    """
    settings = get_settings()
    base = settings.lbu_backend_base_url.rstrip("/")
    try:
        resp = httpx.get(f"{base}/error", timeout=3.0)
        # /error 是后端白名单路径，无 JWT 也可访问，连通即代表服务在线
        return f"LinkBetweenUs 后端（{base}）在线，HTTP 状态码 {resp.status_code}。"
    except httpx.HTTPError:
        return f"LinkBetweenUs 后端（{base}）当前不可达，服务可能未启动。"


# ===== 联网 =====


def web_fetch(url: str) -> str:
    """抓取网页并转为纯文本，供需要查看网页内容时使用。

    url 是要抓取的网页地址（需要以 http:// 或 https:// 开头）。
    返回网页标题、最终地址与正文纯文本（超长截断）；
    图片、下载文件等非文本页面无法抓取。
    """
    settings = get_settings()
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        return f"无效的网址：{url}（需要以 http:// 或 https:// 开头）。"
    try:
        resp = httpx.get(
            url,
            timeout=settings.web_fetch_timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LBU-Agent/0.1"
            },
        )
    except httpx.HTTPError as e:
        return f"网页抓取失败：{e}"
    if resp.status_code >= 400:
        return f"网页返回错误状态码 {resp.status_code}，内容无法获取。"
    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return f"该地址不是文本网页（content-type: {content_type}），无法转为纯文本。"
    title = ""
    if m := re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL):
        title = unescape(m.group(1)).strip()
    text = html2text.html2text(resp.text, baseurl=str(resp.url))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    limit = settings.web_max_fetch_chars
    head = f"网页标题：{title or '（无标题）'}\n网页地址：{resp.url}\n\n{text}"
    if len(head) > limit:
        head = head[:limit] + f"\n\n……（内容过长，以上为前 {limit} 字符）"
    return head


def web_search(query: str) -> str:
    """用 Google 搜索查询词，返回结果的标题、链接与摘要。

    当用户需要查询最新信息、事实、资讯，且没有具体网址可用时使用本工具
    （由 Serper.dev 提供 Google 搜索结果）；如果结果里有合适的链接、
    需要看完整内容时，再用 web_fetch 抓取那个链接。
    """
    settings = get_settings()
    if not settings.serper_api_key:
        return (
            "搜索服务未配置（缺少 SERPER_API_KEY）。"
            "请告知用户搜索功能暂不可用，稍后再试。"
        )
    try:
        resp = httpx.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            json={
                "q": query,
                "gl": settings.web_search_region,
                "hl": "zh-cn",
                "num": settings.web_search_max_results,
            },
            timeout=settings.web_fetch_timeout,
        )
    except httpx.HTTPError as e:
        return f"搜索请求失败：{e}。请告知用户稍后再试。"
    if resp.status_code != 200:
        return f"搜索服务返回错误状态码 {resp.status_code}。请告知用户稍后再试。"
    data = resp.json()
    parts = []
    # 直接答案（天气、汇率等查询会带 answerBox）
    if box := data.get("answerBox"):
        title = box.get("title") or "直接答案"
        answer = box.get("answer") or box.get("snippet") or ""
        if answer:
            parts.append(f"【{title}】{answer}")
    org = data.get("organic") or []
    if not org and not parts:
        return "搜索没有返回任何结果。请告知用户换个关键词再试。"
    lines = []
    for item in org:
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if not title:
            continue
        line = f"- {title}\n  链接：{link}"
        if snippet:
            line += f"\n  摘要：{snippet[:300]}"
        lines.append(line)
    if lines:
        parts.append("搜索结果：\n" + "\n".join(lines))
    out = "\n\n".join(parts)
    limit = settings.web_max_fetch_chars
    if len(out) > limit:
        out = out[:limit] + f"\n\n……（结果较长，以上为前 {limit} 字符）"
    return out


# ===== 注册 =====


def register_tools(mcp: FastMCP) -> None:
    """把全部通用工具挂到 MCP 实例上（新工具在此追加）。"""
    mcp.tool()(list_files)
    mcp.tool()(read_file)
    mcp.tool()(write_file)
    mcp.tool()(append_file)
    mcp.tool()(get_current_time)
    mcp.tool()(check_lbu_backend_health)
    mcp.tool()(web_fetch)
    mcp.tool()(web_search)
