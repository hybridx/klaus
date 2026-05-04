"""Bridge MCP tools into LangChain tools for use in LangGraph agents."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import StructuredTool

from klaus.mcp.manager import MCPServerManager, MCPToolInfo

logger = logging.getLogger(__name__)


def mcp_tool_to_langchain(
    server_name: str,
    tool_info: MCPToolInfo,
    mcp_manager: MCPServerManager,
) -> StructuredTool:
    """Wrap an MCP tool as a LangChain StructuredTool."""

    async def _invoke(**kwargs: Any) -> str:
        result = await mcp_manager.call_tool(server_name, tool_info.name, kwargs)
        if hasattr(result, "content"):
            parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
                else:
                    parts.append(str(block))
            return "\n".join(parts)
        return str(result)

    schema = tool_info.input_schema or {}
    properties = schema.get("properties", {})

    args_schema = None
    if properties:
        from pydantic import create_model

        fields = {}
        for prop_name, prop_info in properties.items():
            prop_type = prop_info.get("type", "string")
            py_type = {"string": str, "integer": int, "number": float, "boolean": bool}.get(
                prop_type, str
            )
            required = prop_name in schema.get("required", [])
            if required:
                fields[prop_name] = (py_type, ...)
            else:
                fields[prop_name] = (py_type | None, None)
        args_schema = create_model(f"{tool_info.name}_Args", **fields)

    return StructuredTool(
        name=tool_info.name,
        description=tool_info.description or f"MCP tool: {tool_info.name}",
        coroutine=_invoke,
        args_schema=args_schema,
    )


def collect_mcp_tools(mcp_manager: MCPServerManager) -> list[StructuredTool]:
    """Collect all tools from all connected MCP servers as LangChain tools."""
    tools = []
    for server_name, server_tools in mcp_manager.get_all_tools().items():
        for tool_info in server_tools:
            try:
                lc_tool = mcp_tool_to_langchain(server_name, tool_info, mcp_manager)
                tools.append(lc_tool)
            except Exception as exc:
                logger.warning(
                    "Failed to convert MCP tool %s/%s: %s",
                    server_name, tool_info.name, exc,
                )
    return tools
