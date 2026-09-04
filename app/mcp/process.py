"""MCP 子进程托管：主服务启动时自动拉起 lbu-tools，退出时回收。

设计：先探测 MCP 端点是否已有服务在应答（复用开发者手动启动的实例，
或 --reload 下前一个 worker 留下的实例），没有再拉起子进程；
拉起失败只记日志，MCP 工具降级为空，不影响主服务与内置工具。
"""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def mcp_reachable() -> bool:
    """MCP 端点是否有服务在应答（任意非 5xx 响应都算在线）。"""
    url = get_settings().mcp_server_url
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(url)
        return resp.status_code < 500
    except httpx.HTTPError:
        return False


async def start_mcp_server() -> subprocess.Popen | None:
    """确保 MCP 服务在线；返回自动拉起的子进程句柄（复用时返回 None）。"""
    settings = get_settings()
    if await mcp_reachable():
        logger.info("MCP 服务已在运行，直接复用: %s", settings.mcp_server_url)
        return None
    logger.info("MCP 服务未运行，自动拉起: %s", settings.mcp_server_url)
    kwargs = {}
    if os.name == "nt":  # Windows 下不弹控制台窗口
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "app.mcp.server"],
            cwd=_PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
    except OSError as e:
        logger.warning("MCP 子进程拉起失败，本次仅使用内置工具: %s", e)
        return None
    for _ in range(20):  # 最多等 10 秒
        if proc.poll() is not None:
            logger.warning(
                "MCP 子进程启动后立即退出（exit=%s），本次仅使用内置工具",
                proc.returncode,
            )
            return None
        if await mcp_reachable():
            logger.info("MCP 服务已就绪")
            return proc
        await asyncio.sleep(0.5)
    logger.warning("等待 MCP 服务就绪超时，本次仅使用内置工具")
    return proc


def stop_mcp_server(proc: subprocess.Popen | None) -> None:
    """回收自动拉起的 MCP 子进程（复用/未拉起的传 None）。"""
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        proc.kill()
