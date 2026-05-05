"""Markdown-based tool definitions — parse .md files into callable LangChain tools.

Format:
    # Tool: tool_name
    Description of what the tool does.

    ## Parameters
    - param_name (type, required): Description
    - param_name (type): Description (optional)

    ## Implementation
    ```python
    async def run(**kwargs) -> str:
        ...
    ```
"""

from __future__ import annotations

import ast
import logging
import re
import textwrap
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

_TOOL_NAME_RE = re.compile(r"^#\s+Tool:\s*(.+)", re.IGNORECASE)
_PARAM_RE = re.compile(
    r"^-\s+(\w+)\s+\((\w+)(?:,\s*(required))?\)(?::\s*(.*))?$"
)
_TYPE_MAP = {
    "string": str, "str": str,
    "integer": int, "int": int,
    "number": float, "float": float,
    "boolean": bool, "bool": bool,
}


def parse_md_tool(path: Path) -> StructuredTool | None:
    """Parse a single Markdown file into a LangChain StructuredTool."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to read MD tool %s: %s", path, exc)
        return None

    lines = text.strip().split("\n")
    if not lines:
        return None

    # Parse tool name from first heading
    name_match = _TOOL_NAME_RE.match(lines[0])
    if not name_match:
        logger.warning("MD tool %s: missing '# Tool: name' heading", path.name)
        return None
    tool_name = name_match.group(1).strip().replace(" ", "_").lower()

    # Parse description (lines after heading until next ##)
    desc_lines = []
    i = 1
    while i < len(lines) and not lines[i].startswith("##"):
        desc_lines.append(lines[i])
        i += 1
    description = "\n".join(desc_lines).strip() or f"Tool from {path.name}"

    # Parse parameters section
    params: dict[str, dict[str, Any]] = {}
    if i < len(lines) and "parameter" in lines[i].lower():
        i += 1
        while i < len(lines) and not lines[i].startswith("##"):
            pm = _PARAM_RE.match(lines[i].strip())
            if pm:
                pname = pm.group(1)
                ptype = pm.group(2).lower()
                required = pm.group(3) is not None
                pdesc = (pm.group(4) or "").strip()
                params[pname] = {
                    "type": _TYPE_MAP.get(ptype, str),
                    "required": required,
                    "description": pdesc,
                }
            i += 1

    # Parse implementation section
    impl_code = None
    while i < len(lines):
        if "implementation" in lines[i].lower():
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                i += 1
            if i < len(lines):
                i += 1  # skip opening ```python
                code_lines = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                impl_code = textwrap.dedent("\n".join(code_lines))
            break
        i += 1

    # Build the callable
    if impl_code:
        try:
            ast.parse(impl_code)
        except SyntaxError as exc:
            logger.warning("MD tool %s has invalid Python: %s", tool_name, exc)
            impl_code = None

    if impl_code:
        namespace: dict[str, Any] = {}
        exec(impl_code, namespace)  # noqa: S102
        run_fn = namespace.get("run")
        if run_fn is None:
            logger.warning("MD tool %s: implementation must define a 'run' function", tool_name)
            return None
    else:
        async def run(**kwargs: Any) -> str:
            return f"Tool '{tool_name}' executed with: {kwargs}"
        run_fn = run

    # Build pydantic args schema
    args_schema = None
    if params:
        from pydantic import create_model

        fields = {}
        for pname, pinfo in params.items():
            if pinfo["required"]:
                fields[pname] = (pinfo["type"], ...)
            else:
                fields[pname] = (pinfo["type"] | None, None)
        args_schema = create_model(f"{tool_name}_Args", **fields)

    return StructuredTool(
        name=tool_name,
        description=description,
        coroutine=run_fn,
        args_schema=args_schema,
    )


def load_md_tools(directory: str | Path) -> list[StructuredTool]:
    """Load all .md tool definitions from a directory."""
    d = Path(directory)
    if not d.exists():
        logger.info("MD tools directory %s does not exist, skipping", d)
        return []

    tools = []
    for path in sorted(d.glob("*.md")):
        tool = parse_md_tool(path)
        if tool:
            tools.append(tool)
            logger.info("Loaded MD tool: %s from %s", tool.name, path.name)

    return tools
