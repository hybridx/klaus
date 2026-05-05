"""MCP server management endpoints — dynamic registration and tool discovery."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from klaus.api.deps import get_state
from klaus.events.bus import EventType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


class RegisterMCPRequest(BaseModel):
    name: str = Field(..., description="Unique name for the MCP server")
    command: str = Field(
        default="",
        description="Command to launch the server (stdio transport)",
    )
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = Field(
        default=None,
        description="SSE endpoint URL (alternative to command)",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers for SSE transport",
    )
    auto_connect: bool = Field(
        default=True,
        description="Connect immediately after registration",
    )


class CallToolRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/servers")
async def list_servers():
    """List all registered MCP servers and their status."""
    state = get_state()
    return {"servers": state.mcp_manager.list_servers()}


@router.post("/servers", status_code=201)
async def register_server(req: RegisterMCPRequest):
    """Register (and optionally connect) a new MCP server at runtime."""
    state = get_state()
    try:
        entry = await state.mcp_manager.register(
            name=req.name,
            command=req.command,
            args=req.args,
            env=req.env,
            url=req.url,
            headers=req.headers,
            auto_connect=req.auto_connect,
        )
        return {
            "name": entry.name,
            "status": entry.status.value,
            "tools": [{"name": t.name, "description": t.description} for t in entry.tools],
        }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/servers/{name}")
async def unregister_server(name: str):
    """Unregister and disconnect an MCP server."""
    state = get_state()
    try:
        await state.mcp_manager.unregister(name)
        return {"status": "removed", "name": name}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/servers/{name}/connect")
async def connect_server(name: str, request: Request):
    """Connect to a registered MCP server.

    For URL-based servers that require OAuth, the SDK handles the full
    PKCE flow automatically.  If authorization is needed the response
    includes an ``auth_url`` that the UI should open in a new tab.
    """
    state = get_state()
    try:
        entry = state.mcp_manager._get(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    base = str(request.base_url).rstrip("/")
    base = base.replace("://0.0.0.0", "://localhost")
    callback_url = f"{base}/api/mcp/auth/callback"

    with contextlib.suppress(Exception):
        await state.mcp_manager.connect(
            name, callback_url=callback_url,
        )

    return {
        "status": entry.status.value,
        "name": name,
        "tools": [
            {"name": t.name, "description": t.description}
            for t in entry.tools
        ],
        "error": entry.error,
        "auth_url": entry._auth_url,
    }


@router.get("/servers/{name}/tools")
async def list_tools(name: str):
    """List tools exposed by an MCP server."""
    state = get_state()
    try:
        tools = state.mcp_manager.get_tools(name)
        return {
            "server": name,
            "tools": [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ],
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/servers/{name}/call")
async def call_tool(name: str, req: CallToolRequest):
    """Invoke a tool on an MCP server."""
    state = get_state()
    try:
        result = await state.mcp_manager.call_tool(name, req.tool_name, req.arguments)
        return {"server": name, "tool": req.tool_name, "result": str(result)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tools")
async def list_all_tools():
    """List all tools across all connected MCP servers."""
    state = get_state()
    all_tools = state.mcp_manager.get_all_tools()
    return {
        server: [
            {"name": t.name, "description": t.description}
            for t in tools
        ]
        for server, tools in all_tools.items()
    }


# ------------------------------------------------------------------
# OAuth callback — the MCP SDK's OAuthClientProvider redirects here
# ------------------------------------------------------------------


@router.get("/auth/callback", response_class=HTMLResponse)
async def oauth_callback(request: Request):
    """OAuth2 callback — signals the SDK to complete the token exchange.

    After the user consents in the browser, the OAuth provider redirects
    here with ``code`` and ``state`` query parameters.  We pass these to
    the manager which unblocks the SDK's ``callback_handler``.
    """
    code = request.query_params.get("code")
    state_token = request.query_params.get("state")

    if not code:
        return HTMLResponse(
            "<h2>Authorization failed</h2>"
            "<p>Missing authorization code.</p>",
            status_code=400,
        )

    state = get_state()

    try:
        server_name = state.mcp_manager.receive_auth_callback(
            code, state_token,
        )
    except ValueError as exc:
        return HTMLResponse(
            f"<h2>Authorization failed</h2><p>{exc!s}</p>",
            status_code=400,
        )

    await asyncio.sleep(3)

    state.event_bus.emit(
        EventType.MCP_REGISTERED,
        {"name": server_name, "event": "auth_complete"},
    )

    return HTMLResponse(
        f"<h2>Authorization successful!</h2>"
        f"<p>MCP server <b>{server_name}</b> is authenticating. "
        f"You can close this tab.</p>"
        f"<script>window.close()</script>",
    )
