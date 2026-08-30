"""TraceForce coding agent public API."""

from traceforce.agent import CodingAgent, build_coding_tools
from traceforce.identity import (
    DEVELOPER_HANDLE,
    DEVELOPER_NAME,
    PRODUCT_NAME,
    PROJECT_NAME,
    PURPOSE,
    REPOSITORY_URL,
    TAGLINE,
    VERSION,
    WORKFLOW,
)
from traceforce.mcp import MCPClientManager, MCPConnection, MCPServerConfig

__all__ = [
    "CodingAgent",
    "build_coding_tools",
    "DEVELOPER_HANDLE",
    "DEVELOPER_NAME",
    "MCPServerConfig",
    "MCPConnection",
    "MCPClientManager",
    "PRODUCT_NAME",
    "PROJECT_NAME",
    "PURPOSE",
    "REPOSITORY_URL",
    "TAGLINE",
    "VERSION",
    "WORKFLOW",
]
