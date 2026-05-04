"""Dynamic MCP server manager — register, connect, and invoke MCP servers at runtime."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPServerStatus(StrEnum):
    REGISTERED = "registered"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class MCPToolInfo:
    name: str
    description: str | None
    input_schema: dict[str, Any] | None


@dataclass
class MCPServerEntry:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    status: MCPServerStatus = MCPServerStatus.REGISTERED
    tools: list[MCPToolInfo] = field(default_factory=list)
    error: str | None = None

    # Runtime handles — not serialized
    _session: ClientSession | None = field(default=None, repr=False)
    _read: Any = field(default=None, repr=False)
    _write: Any = field(default=None, repr=False)
    _cm: Any = field(default=None, repr=False)
    _task: asyncio.Task | None = field(default=None, repr=False)


class MCPServerManager:
    """Manages MCP server lifecycle: register, connect, discover tools, call tools.

    Servers can be added/removed at runtime via the API. Each server runs as a
    subprocess (stdio transport) managed by the official MCP Python SDK.
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerEntry] = {}

    async def register(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        auto_connect: bool = True,
    ) -> MCPServerEntry:
        if name in self._servers:
            raise ValueError(f"MCP server '{name}' is already registered")

        entry = MCPServerEntry(
            name=name,
            command=command,
            args=args or [],
            env=env or {},
        )
        self._servers[name] = entry
        logger.info("Registered MCP server: %s (%s)", name, command)

        if auto_connect:
            await self.connect(name)

        return entry

    async def connect(self, name: str) -> None:
        entry = self._get(name)
        if entry.status == MCPServerStatus.CONNECTED:
            return

        try:
            server_params = StdioServerParameters(
                command=entry.command,
                args=entry.args,
                env=entry.env if entry.env else None,
            )

            read_stream, write_stream = await self._start_server(server_params)
            entry._read = read_stream
            entry._write = write_stream

            session = ClientSession(read_stream, write_stream)
            await session.initialize()
            entry._session = session
            entry.status = MCPServerStatus.CONNECTED

            tools_result = await session.list_tools()
            entry.tools = [
                MCPToolInfo(
                    name=t.name,
                    description=t.description,
                    input_schema=t.inputSchema if hasattr(t, "inputSchema") else None,
                )
                for t in tools_result.tools
            ]

            logger.info(
                "Connected to MCP server '%s' — %d tools available",
                name,
                len(entry.tools),
            )
        except Exception as exc:
            entry.status = MCPServerStatus.ERROR
            entry.error = str(exc)
            logger.error("Failed to connect to MCP server '%s': %s", name, exc)
            raise

    async def _start_server(self, params: StdioServerParameters) -> tuple:
        """Start an MCP stdio server and return (read_stream, write_stream)."""
        cm = stdio_client(params)
        streams = await cm.__aenter__()
        return streams

    async def disconnect(self, name: str) -> None:
        entry = self._get(name)
        if entry._session:
            try:
                # Close session resources
                entry._session = None
            except Exception as exc:
                logger.warning("Error disconnecting MCP server '%s': %s", name, exc)
        entry.status = MCPServerStatus.DISCONNECTED
        entry.tools = []
        logger.info("Disconnected MCP server: %s", name)

    async def unregister(self, name: str) -> None:
        if name in self._servers:
            await self.disconnect(name)
            del self._servers[name]
            logger.info("Unregistered MCP server: %s", name)

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        entry = self._get(server_name)
        if entry._session is None or entry.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"MCP server '{server_name}' is not connected")

        result = await entry._session.call_tool(tool_name, arguments)
        return result

    def list_servers(self) -> list[dict[str, Any]]:
        return [
            {
                "name": e.name,
                "command": e.command,
                "args": e.args,
                "status": e.status.value,
                "tools": [
                    {"name": t.name, "description": t.description}
                    for t in e.tools
                ],
                "error": e.error,
            }
            for e in self._servers.values()
        ]

    def get_tools(self, server_name: str) -> list[MCPToolInfo]:
        return self._get(server_name).tools

    def get_all_tools(self) -> dict[str, list[MCPToolInfo]]:
        return {name: entry.tools for name, entry in self._servers.items()}

    async def shutdown_all(self) -> None:
        for name in list(self._servers):
            try:
                await self.unregister(name)
            except Exception as exc:
                logger.warning("Error shutting down MCP server '%s': %s", name, exc)

    def _get(self, name: str) -> MCPServerEntry:
        entry = self._servers.get(name)
        if entry is None:
            available = list(self._servers.keys())
            raise KeyError(f"MCP server '{name}' not found. Available: {available}")
        return entry
