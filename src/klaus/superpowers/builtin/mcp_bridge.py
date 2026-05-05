"""MCP Bridge superpower — wraps all connected MCP servers as a single capability.

This is a built-in superpower that auto-registers. It bridges the MCP server
manager into the superpower/memory system so the agent sees MCP tools as
part of its superpower tree. Also includes MD-based tool definitions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

from klaus.agents.tools import collect_mcp_tools
from klaus.superpowers.base import Superpower

if TYPE_CHECKING:
    from klaus.mcp.manager import MCPServerManager


class MCPBridge(Superpower):
    """Exposes all connected MCP server tools and MD-based tools to the agent."""

    def __init__(
        self,
        mcp_manager: MCPServerManager,
        md_tools: list[BaseTool] | None = None,
    ) -> None:
        super().__init__()
        self._mcp = mcp_manager
        self._md_tools = md_tools or []

    @property
    def name(self) -> str:
        return "mcp"

    @property
    def description(self) -> str:
        servers = self._mcp.list_servers()
        count = len(servers)
        md_count = len(self._md_tools)
        parts = []
        if count:
            parts.append(f"{count} server{'s' if count != 1 else ''}")
        if md_count:
            parts.append(f"{md_count} MD tool{'s' if md_count != 1 else ''}")
        return f"MCP tool bridge ({', '.join(parts) or 'no tools'})"

    @property
    def tags(self) -> list[str]:
        return ["tools", "mcp", "bridge"]

    async def activate(self) -> None:
        await super().activate()
        for server in self._mcp.list_servers():
            name = server["name"]
            tools = server.get("tools", [])
            tool_names = [t["name"] for t in tools]
            self.remember(
                f"servers/{name}",
                f"MCP server with tools: {', '.join(tool_names)}",
                metadata={"status": server["status"], "tool_count": len(tools)},
                tags=["mcp-server"],
            )
        for tool in self._md_tools:
            self.remember(
                f"md_tools/{tool.name}",
                f"MD tool: {tool.description}",
                metadata={"source": "markdown"},
                tags=["md-tool"],
            )

    def get_tools(self) -> list[BaseTool]:
        mcp_tools = collect_mcp_tools(self._mcp)
        return mcp_tools + list(self._md_tools)
