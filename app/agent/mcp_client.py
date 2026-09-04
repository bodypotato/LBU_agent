"""MCP 客户端：通过 langchain-mcp-adapters 加载 lbu-tools 的工具。

MCP 服务不可达时降级为空工具集（只记日志），agent 仍可用内置工具
（RAG 检索 / 技能加载）；服务恢复后调用 clear_mcp_tools_cache 再重新加载。
"""

import logging

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: MultiServerMCPClient | None = None
_tools: list | None = None


async def load_mcp_tools() -> list:
    """加载 lbu-tools MCP 服务的全部工具（进程内缓存）。"""
    global _client, _tools
    if _tools is None:
        url = get_settings().mcp_server_url
        try:
            _client = MultiServerMCPClient(
                {"lbu-tools": {"url": url, "transport": "http"}}
            )
            _tools = await _client.get_tools()
        except Exception as e:  # noqa: BLE001 —— MCP 不可达只降级，不影响主流程
            logger.warning("MCP 工具加载失败（%s），本次仅使用内置工具: %s", url, e)
            _tools = []
        if _tools:
            logger.info("已从 MCP 服务加载 %d 个工具: %s", len(_tools), [t.name for t in _tools])
    return _tools


def clear_mcp_tools_cache() -> None:
    """清空 MCP 工具缓存（MCP 服务重启/恢复后调用，下次加载重新连接）。"""
    global _client, _tools
    _client = None
    _tools = None


async def close_mcp_client() -> None:
    """关闭与 MCP 服务的全部会话（应用退出时调用）。"""
    global _client
    if _client is not None:
        try:
            await _client.__aexit__(None, None, None)
        except Exception as e:  # noqa: BLE001 —— 关闭失败只记日志
            logger.debug("关闭 MCP 客户端会话失败: %s", e)
        _client = None
