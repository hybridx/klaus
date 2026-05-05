"""Dynamic MCP server manager — register, connect, and invoke MCP servers at runtime."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


class MCPTransport(StrEnum):
    STDIO = "stdio"
    SSE = "sse"


class MCPServerStatus(StrEnum):
    REGISTERED = "registered"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    NEEDS_AUTH = "needs_auth"
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
    url: str | None = field(default=None)
    headers: dict[str, str] = field(default_factory=dict)
    transport: MCPTransport = MCPTransport.STDIO
    status: MCPServerStatus = MCPServerStatus.REGISTERED
    tools: list[MCPToolInfo] = field(default_factory=list)
    error: str | None = None

    # Runtime handles — not serialized
    _session: ClientSession | None = field(default=None, repr=False)
    _read: Any = field(default=None, repr=False)
    _write: Any = field(default=None, repr=False)
    _cm: Any = field(default=None, repr=False)
    _task: asyncio.Task | None = field(default=None, repr=False)


def _extract_auth_error(entry: MCPServerEntry, exc: BaseException) -> None:
    """Detect 401/403 in nested ExceptionGroups and mark as needs_auth."""
    msg = str(exc).lower()
    if "401" in msg or "unauthorized" in msg or "403" in msg:
        entry.status = MCPServerStatus.NEEDS_AUTH
        entry.error = (
            "Authentication required. Add an auth token or "
            "API key in the server's headers."
        )
        return
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            _extract_auth_error(entry, sub)
            if entry.status == MCPServerStatus.NEEDS_AUTH:
                return


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
        command: str = "",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        auto_connect: bool = True,
    ) -> MCPServerEntry:
        if name in self._servers:
            raise ValueError(f"MCP server '{name}' is already registered")

        transport = MCPTransport.SSE if url else MCPTransport.STDIO

        entry = MCPServerEntry(
            name=name,
            command=command,
            args=args or [],
            env=env or {},
            url=url,
            headers=headers or {},
            transport=transport,
        )
        self._servers[name] = entry
        logger.info("Registered MCP server: %s (%s, transport=%s)", name, url or command, transport)

        if auto_connect:
            await self.connect(name)

        return entry

    CONNECTION_TIMEOUT = 15  # seconds

    async def connect(self, name: str) -> None:
        entry = self._get(name)
        if entry.status == MCPServerStatus.CONNECTED:
            return

        try:
            ready: asyncio.Future[None] = asyncio.get_event_loop().create_future()

            async def _run_session(read_stream, write_stream) -> None:
                """Common session init + tool discovery, then wait forever."""
                session = ClientSession(read_stream, write_stream)
                await asyncio.wait_for(
                    session.initialize(), timeout=self.CONNECTION_TIMEOUT,
                )
                entry._session = session
                entry.status = MCPServerStatus.CONNECTED

                tools_result = await asyncio.wait_for(
                    session.list_tools(), timeout=self.CONNECTION_TIMEOUT,
                )
                entry.tools = [
                    MCPToolInfo(
                        name=t.name,
                        description=t.description,
                        input_schema=t.inputSchema if hasattr(t, "inputSchema") else None,
                    )
                    for t in tools_result.tools
                ]

                logger.info(
                    "Connected to MCP server '%s' (%s) — %d tools available",
                    name, entry.transport, len(entry.tools),
                )

                if not ready.done():
                    ready.set_result(None)

                await asyncio.Future()

            async def _open_url_transport(url, hdrs):
                """Try streamable HTTP first, fall back to SSE."""
                try:
                    cm = streamablehttp_client(
                        url=url,
                        headers=hdrs if hdrs else None,
                    )
                    streams = await cm.__aenter__()
                    read_s, write_s = streams[0], streams[1]
                    return cm, read_s, write_s
                except Exception:
                    cm2 = sse_client(
                        url=url,
                        headers=hdrs if hdrs else None,
                    )
                    streams2 = await cm2.__aenter__()
                    return cm2, streams2[0], streams2[1]

            async def _server_lifecycle() -> None:
                cm = None
                try:
                    if entry.transport == MCPTransport.SSE:
                        cm, read_s, write_s = await _open_url_transport(
                            entry.url, entry.headers,
                        )
                        entry._read = read_s
                        entry._write = write_s
                        entry._cm = cm
                        await _run_session(read_s, write_s)
                    else:
                        server_params = StdioServerParameters(
                            command=entry.command,
                            args=entry.args,
                            env=entry.env if entry.env else None,
                        )
                        async with stdio_client(
                            server_params,
                        ) as (read_stream, write_stream):
                            entry._read = read_stream
                            entry._write = write_stream
                            await _run_session(
                                read_stream, write_stream,
                            )

                except asyncio.CancelledError:
                    logger.debug(
                        "MCP server '%s' lifecycle cancelled", name,
                    )
                except BaseException as exc:
                    _extract_auth_error(entry, exc)
                    if not ready.done():
                        ready.set_exception(exc)
                        return
                    logger.debug(
                        "MCP server '%s' disconnect error: %s",
                        name, exc,
                    )
                finally:
                    entry._session = None
                    if entry.status != MCPServerStatus.ERROR:
                        entry.status = MCPServerStatus.DISCONNECTED
                    if cm is not None:
                        with contextlib.suppress(Exception):
                            await cm.__aexit__(None, None, None)

            task = asyncio.create_task(_server_lifecycle(), name=f"mcp-{name}")
            entry._task = task

            await asyncio.wait_for(asyncio.shield(ready), timeout=self.CONNECTION_TIMEOUT)

        except BaseException as exc:
            _extract_auth_error(entry, exc)
            if entry.status != MCPServerStatus.NEEDS_AUTH:
                entry.status = MCPServerStatus.ERROR
                entry.error = str(exc)
            if entry._task and not entry._task.done():
                entry._task.cancel()
                entry._task = None
            logger.error(
                "Failed to connect to MCP server '%s': %s",
                name, exc,
            )
            raise

    async def disconnect(self, name: str) -> None:
        entry = self._get(name)
        if entry._task and not entry._task.done():
            entry._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await entry._task
            entry._task = None
        entry._session = None
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
                "url": e.url,
                "transport": e.transport.value,
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
