"""MCP server management endpoints — dynamic registration and tool discovery."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from klaus.api.deps import get_state

router = APIRouter(prefix="/mcp", tags=["mcp"])


class RegisterMCPRequest(BaseModel):
    name: str = Field(..., description="Unique name for the MCP server")
    command: str = Field(..., description="Command to launch the server")
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    auto_connect: bool = Field(default=True, description="Connect immediately after registration")


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
async def connect_server(name: str):
    """Connect to a registered but disconnected MCP server."""
    state = get_state()
    try:
        await state.mcp_manager.connect(name)
        return {"status": "connected", "name": name}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
