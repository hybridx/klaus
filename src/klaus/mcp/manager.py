"""Dynamic MCP server manager — register, connect, and invoke MCP servers at runtime.

Uses the MCP SDK's built-in OAuthClientProvider for authentication. When a
server returns 401, the SDK automatically handles OAuth metadata discovery,
dynamic client registration, PKCE authorization, and token exchange — exactly
like Cursor does for Atlassian and other OAuth-enabled MCP servers.

For stdio servers that write non-JSON banners to stdout (e.g. "Server running
on stdio"), a ``LenientReadStream`` wrapper silently drops parse-error
exceptions so the session isn't killed — matching Cursor's TypeScript client
behaviour.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.auth import OAuthClientProvider
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken
from mcp.shared.message import SessionMessage

logger = logging.getLogger(__name__)


class LenientReadStream:
    """Wraps an MCP read stream to silently drop non-JSON parse errors.

    The MCP Python SDK's ``stdio_client`` sends ``Exception`` objects into
    the read stream whenever a line from stdout can't be parsed as JSON-RPC.
    Some servers (e.g. ``@scarlet-mesh/mcp-products``) write human-readable
    banners to stdout before the first JSON message. Cursor's TypeScript
    client ignores these; the Python SDK crashes the ``ClientSession``.

    This wrapper intercepts those exceptions so the session only sees valid
    ``SessionMessage`` objects — matching Cursor's lenient behaviour.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def __aenter__(self) -> LenientReadStream:
        if hasattr(self._inner, "__aenter__"):
            await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if hasattr(self._inner, "__aexit__"):
            await self._inner.__aexit__(*exc_info)

    async def receive(self) -> SessionMessage:
        while True:
            item = await self._inner.receive()
            if isinstance(item, Exception):
                logger.debug(
                    "Skipping non-JSON MCP message: %s", item,
                )
                continue
            return item

    async def aclose(self) -> None:
        await self._inner.aclose()

    def __aiter__(self) -> LenientReadStream:
        return self

    async def __anext__(self) -> SessionMessage:
        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration from None


class MCPTransport(StrEnum):
    STDIO = "stdio"
    SSE = "sse"


class MCPServerStatus(StrEnum):
    REGISTERED = "registered"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    NEEDS_AUTH = "needs_auth"
    AWAITING_AUTH = "awaiting_auth"
    ERROR = "error"


@dataclass
class MCPToolInfo:
    name: str
    description: str | None
    input_schema: dict[str, Any] | None


class InMemoryTokenStorage:
    """Stores OAuth tokens and client registration in memory (per server).

    Tokens survive reconnections within the same process. A future version
    could persist to disk / DB for cross-restart persistence.
    """

    def __init__(self) -> None:
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info = client_info


def _is_cleanup_noise(exc: BaseException) -> bool:
    """Return True for BrokenResourceError / ClosedResourceError from task cancellation.

    When a stdio server is killed during shutdown (or the connection is cancelled
    mid-handshake), anyio raises BrokenResourceError/ClosedResourceError wrapped
    in an ExceptionGroup. These are expected cleanup artefacts, not real errors.
    """
    from anyio import BrokenResourceError, ClosedResourceError

    noise_types = (BrokenResourceError, ClosedResourceError)
    if isinstance(exc, noise_types):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return all(_is_cleanup_noise(e) for e in exc.exceptions)
    return False


def _is_auth_error(exc: BaseException) -> bool:
    """Heuristic check for 401/403 errors buried in exception chains."""
    msg = str(exc).lower()
    if "401" in msg or "unauthorized" in msg or "403" in msg:
        return True
    if (
        hasattr(exc, "response")
        and hasattr(exc.response, "status_code")
        and exc.response.status_code in (401, 403)
    ):
        return True
    if exc.__cause__ and _is_auth_error(exc.__cause__):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_auth_error(e) for e in exc.exceptions)
    return False


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

    # SDK-based OAuth state
    _token_storage: InMemoryTokenStorage | None = field(default=None, repr=False)
    _auth_url: str | None = field(default=None, repr=False)
    _auth_event: asyncio.Event | None = field(default=None, repr=False)
    _auth_code: str | None = field(default=None, repr=False)
    _auth_state: str | None = field(default=None, repr=False)

    _session: ClientSession | None = field(default=None, repr=False)
    _read: Any = field(default=None, repr=False)
    _write: Any = field(default=None, repr=False)
    _cm: Any = field(default=None, repr=False)
    _task: asyncio.Task | None = field(default=None, repr=False)


class MCPServerManager:
    """Manages MCP server lifecycle: register, connect, discover tools, call tools.

    Servers can be added/removed at runtime via the API. Each server runs as a
    background asyncio task managed by the official MCP Python SDK.
    """

    CONNECTION_TIMEOUT = 15  # seconds — for session.initialize() and list_tools()
    STDIO_STARTUP_TIMEOUT = 45  # seconds — for npx/stdio servers (includes package download)

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
        if url:
            entry._token_storage = InMemoryTokenStorage()
        self._servers[name] = entry

        logger.info(
            "Registered MCP server: %s (%s, transport=%s)",
            name, url or command, transport,
        )

        if auto_connect:
            with contextlib.suppress(Exception):
                await self.connect(name)

        return entry

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(
        self,
        name: str,
        *,
        callback_url: str | None = None,
    ) -> None:
        """Connect to an MCP server.

        For URL-based servers that need OAuth, pass *callback_url* so the SDK
        can register it as a redirect URI. When the server returns 401 the
        SDK handles the full OAuth2 PKCE flow:

        1.  ``redirect_handler`` fires with the authorization URL.
        2.  The connect call returns with ``status=awaiting_auth``.
        3.  The user opens the URL, consents in the browser.
        4.  The browser redirects to *callback_url* with ``code`` and ``state``.
        5.  The callback endpoint calls ``receive_auth_callback``.
        6.  The SDK exchanges the code for a token and reconnects.
        """
        entry = self._get(name)
        if entry.status == MCPServerStatus.CONNECTED:
            return

        if entry.status == MCPServerStatus.AWAITING_AUTH and entry._auth_url:
            return

        # Cancel any previous lifecycle task
        if entry._task and not entry._task.done():
            entry._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await entry._task
            entry._task = None

        # Reset state for a fresh connection attempt
        entry.error = None
        entry._auth_url = None
        entry._auth_event = asyncio.Event()
        entry._auth_code = None
        entry._auth_state = None

        initial_done = asyncio.Event()

        # ── OAuth handlers (called by the MCP SDK internally) ────
        async def redirect_handler(authorize_url: str) -> None:
            entry._auth_url = authorize_url
            entry.status = MCPServerStatus.AWAITING_AUTH
            initial_done.set()
            logger.info(
                "OAuth consent needed for '%s' — URL: %s…",
                name, authorize_url[:120],
            )

        async def callback_handler() -> tuple[str, str | None]:
            logger.info("Waiting for OAuth callback for '%s'…", name)
            assert entry._auth_event is not None
            await entry._auth_event.wait()
            return entry._auth_code or "", entry._auth_state

        # ── Session init (shared by both transports) ─────────────
        async def _run_session(read_stream: Any, write_stream: Any) -> None:
            async with ClientSession(read_stream, write_stream) as session:
                await asyncio.wait_for(
                    session.initialize(), timeout=self.CONNECTION_TIMEOUT,
                )
                entry._session = session
                entry.status = MCPServerStatus.CONNECTED
                entry.error = None

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

                initial_done.set()
                await asyncio.Future()  # keep session alive

        # ── URL transport (streamable HTTP → SSE fallback) ───────
        async def _open_url_transport(
            url: str,
            hdrs: dict[str, str],
            auth_provider: OAuthClientProvider | None,
        ) -> tuple[Any, Any, Any]:
            try:
                cm = streamablehttp_client(
                    url=url,
                    headers=hdrs if hdrs else None,
                    auth=auth_provider,
                )
                streams = await cm.__aenter__()
                return cm, streams[0], streams[1]
            except Exception:
                if entry.status == MCPServerStatus.AWAITING_AUTH:
                    raise
                logger.debug(
                    "Streamable HTTP failed for '%s', trying SSE", name,
                )
                cm2 = sse_client(url=url, headers=hdrs if hdrs else None)
                streams2 = await cm2.__aenter__()
                return cm2, streams2[0], streams2[1]

        # ── Lifecycle task (runs in background) ──────────────────
        async def _server_lifecycle() -> None:
            cm = None
            try:
                if entry.transport == MCPTransport.SSE:
                    auth_provider: OAuthClientProvider | None = None
                    if entry._token_storage and callback_url:
                        client_metadata = OAuthClientMetadata(
                            client_name="Klaus",
                            redirect_uris=[callback_url],
                        )
                        auth_provider = OAuthClientProvider(
                            server_url=entry.url or "",
                            client_metadata=client_metadata,
                            storage=entry._token_storage,
                            redirect_handler=redirect_handler,
                            callback_handler=callback_handler,
                            timeout=300.0,
                        )

                    cm, read_s, write_s = await _open_url_transport(
                        entry.url or "", entry.headers, auth_provider,
                    )
                    entry._read = read_s
                    entry._write = write_s
                    entry._cm = cm
                    await _run_session(read_s, write_s)
                else:
                    merged_env = {**os.environ, **entry.env}
                    server_params = StdioServerParameters(
                        command=entry.command,
                        args=entry.args,
                        env=merged_env,
                    )
                    async with stdio_client(server_params) as (r, w):
                        filtered = LenientReadStream(r)
                        entry._read = filtered
                        entry._write = w
                        await _run_session(filtered, w)

            except asyncio.CancelledError:
                logger.debug("MCP server '%s' lifecycle cancelled", name)
            except BaseException as exc:
                if _is_cleanup_noise(exc):
                    logger.debug(
                        "MCP server '%s' cleanup noise: %s",
                        name, type(exc).__name__,
                    )
                elif entry.status != MCPServerStatus.AWAITING_AUTH:
                    if _is_auth_error(exc):
                        entry.status = MCPServerStatus.NEEDS_AUTH
                        entry.error = "Authentication required — click Connect to authorize."
                    else:
                        entry.status = MCPServerStatus.ERROR
                        err_name = type(exc).__name__
                        entry.error = f"{err_name}: {exc}" if str(exc) else err_name
                    logger.error(
                        "MCP server '%s' error: [%s] %r",
                        name, type(exc).__name__, exc,
                    )
                initial_done.set()
            finally:
                entry._session = None
                if entry.status not in (
                    MCPServerStatus.ERROR,
                    MCPServerStatus.NEEDS_AUTH,
                    MCPServerStatus.AWAITING_AUTH,
                ):
                    entry.status = MCPServerStatus.DISCONNECTED
                if cm is not None:
                    with contextlib.suppress(Exception):
                        await cm.__aexit__(None, None, None)

        # ── Launch and wait ──────────────────────────────────────
        task = asyncio.create_task(_server_lifecycle(), name=f"mcp-{name}")
        entry._task = task

        startup_timeout = (
            self.STDIO_STARTUP_TIMEOUT
            if entry.transport == MCPTransport.STDIO
            else self.CONNECTION_TIMEOUT
        )
        try:
            await asyncio.wait_for(
                initial_done.wait(), timeout=startup_timeout,
            )
        except TimeoutError:
            if entry.status not in (
                MCPServerStatus.AWAITING_AUTH,
                MCPServerStatus.CONNECTED,
            ):
                entry.status = MCPServerStatus.ERROR
                entry.error = "Connection timed out"
                if entry._task and not entry._task.done():
                    entry._task.cancel()
                    entry._task = None

        if entry.status == MCPServerStatus.ERROR:
            raise ConnectionError(entry.error or "Connection failed")

    # ------------------------------------------------------------------
    # OAuth callback (called by the /api/mcp/auth/callback endpoint)
    # ------------------------------------------------------------------

    def receive_auth_callback(self, code: str, state: str | None = None) -> str:
        """Signal a pending OAuth flow with the received authorization code.

        Returns the server name that was waiting for authorization.
        """
        for entry in self._servers.values():
            if (
                entry.status == MCPServerStatus.AWAITING_AUTH
                and entry._auth_event is not None
            ):
                entry._auth_code = code
                entry._auth_state = state
                entry._auth_event.set()
                logger.info(
                    "OAuth callback received for '%s'", entry.name,
                )
                return entry.name

        raise ValueError("No server awaiting OAuth callback")

    # ------------------------------------------------------------------
    # Disconnect / Unregister
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any],
    ) -> Any:
        entry = self._get(server_name)
        if entry._session is None or entry.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"MCP server '{server_name}' is not connected")
        return await entry._session.call_tool(tool_name, arguments)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_servers(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for e in self._servers.values():
            result.append({
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
                "auth_url": e._auth_url,
            })
        return result

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
