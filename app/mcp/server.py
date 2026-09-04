"""lbu-tools MCP 服务：通用能力工具的独立进程宿主（streamable HTTP 传输）。

启动方式：
    uv run python -m app.mcp.server

主服务（main.py）启动时会自动拉起本进程，无需手动启动；
也支持独立运行，供其他 MCP 客户端（如 Claude Desktop）直接接入。

端点：http://127.0.0.1:<MCP_SERVER_PORT>/mcp
"""

import logging

from mcp.server.fastmcp import FastMCP

from app.config import get_settings
from app.mcp.tools import register_tools

logger = logging.getLogger(__name__)


def build_mcp() -> FastMCP:
    """构造 MCP 实例（工具清单见 app/mcp/tools.py 的 register_tools）。"""
    settings = get_settings()
    mcp = FastMCP(
        "lbu-tools",
        instructions=(
            "LinkBetweenUs 的 AI 助手通用工具集：工作区文件读写、时间查询、"
            "后端健康探测、网页抓取。"
        ),
        host="127.0.0.1",
        port=settings.mcp_server_port,
        log_level="INFO",
    )
    register_tools(mcp)
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    port = get_settings().mcp_server_port
    logger.info("lbu-tools MCP 服务启动: http://127.0.0.1:%s/mcp", port)
    build_mcp().run(transport="streamable-http")


if __name__ == "__main__":
    main()
