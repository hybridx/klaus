"""Tests for the MD-based tool parser."""

from __future__ import annotations

import asyncio
from pathlib import Path
from textwrap import dedent

import pytest

from klaus.mcp.md_tools import load_md_tools, parse_md_tool


@pytest.fixture()
def tmp_tools_dir(tmp_path: Path) -> Path:
    return tmp_path / "tools"


def _write_tool(d: Path, name: str, content: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.md"
    p.write_text(dedent(content))
    return p


class TestParseMdTool:
    def test_valid_tool(self, tmp_tools_dir: Path):
        path = _write_tool(tmp_tools_dir, "greet", """\
        # Tool: greet
        Say hello.

        ## Parameters
        - name (string, required): Who to greet

        ## Implementation
        ```python
        async def run(name: str) -> str:
            return f"Hello, {name}!"
        ```
        """)
        tool = parse_md_tool(path)
        assert tool is not None
        assert tool.name == "greet"
        assert "hello" in tool.description.lower()

    def test_missing_heading(self, tmp_tools_dir: Path):
        path = _write_tool(tmp_tools_dir, "bad", """\
        No heading here.
        """)
        tool = parse_md_tool(path)
        assert tool is None

    def test_tool_without_implementation(self, tmp_tools_dir: Path):
        path = _write_tool(tmp_tools_dir, "stub", """\
        # Tool: stub
        A stub tool with no code.

        ## Parameters
        - x (integer, required): A number
        """)
        tool = parse_md_tool(path)
        assert tool is not None
        assert tool.name == "stub"

    def test_tool_with_invalid_python(self, tmp_tools_dir: Path):
        path = _write_tool(tmp_tools_dir, "broken", """\
        # Tool: broken
        Broken impl.

        ## Implementation
        ```python
        def run( this is invalid syntax
        ```
        """)
        tool = parse_md_tool(path)
        # Should fall back to stub run()
        assert tool is not None
        assert tool.name == "broken"

    def test_tool_name_normalization(self, tmp_tools_dir: Path):
        path = _write_tool(tmp_tools_dir, "My Tool", """\
        # Tool: My Cool Tool
        Description.
        """)
        tool = parse_md_tool(path)
        assert tool is not None
        assert tool.name == "my_cool_tool"

    def test_nonexistent_file(self, tmp_path: Path):
        tool = parse_md_tool(tmp_path / "nope.md")
        assert tool is None


class TestLoadMdTools:
    def test_empty_directory(self, tmp_tools_dir: Path):
        tmp_tools_dir.mkdir(parents=True)
        tools = load_md_tools(tmp_tools_dir)
        assert tools == []

    def test_nonexistent_directory(self, tmp_path: Path):
        tools = load_md_tools(tmp_path / "does_not_exist")
        assert tools == []

    def test_loads_multiple_tools(self, tmp_tools_dir: Path):
        _write_tool(tmp_tools_dir, "alpha", """\
        # Tool: alpha
        First tool.
        """)
        _write_tool(tmp_tools_dir, "beta", """\
        # Tool: beta
        Second tool.
        """)
        tools = load_md_tools(tmp_tools_dir)
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"alpha", "beta"}

    def test_skips_invalid_files(self, tmp_tools_dir: Path):
        _write_tool(tmp_tools_dir, "good", """\
        # Tool: good
        Valid tool.
        """)
        _write_tool(tmp_tools_dir, "bad", """\
        Not a valid tool file.
        """)
        tools = load_md_tools(tmp_tools_dir)
        assert len(tools) == 1
        assert tools[0].name == "good"


class TestToolExecution:
    @pytest.mark.asyncio
    async def test_run_with_implementation(self, tmp_tools_dir: Path):
        _write_tool(tmp_tools_dir, "adder", """\
        # Tool: adder
        Add two numbers.

        ## Parameters
        - a (integer, required): First number
        - b (integer, required): Second number

        ## Implementation
        ```python
        async def run(a: int, b: int) -> str:
            return str(a + b)
        ```
        """)
        tool = parse_md_tool(tmp_tools_dir / "adder.md")
        assert tool is not None
        result = await tool.ainvoke({"a": 2, "b": 3})
        assert result == "5"

    @pytest.mark.asyncio
    async def test_run_without_implementation(self, tmp_tools_dir: Path):
        _write_tool(tmp_tools_dir, "echo", """\
        # Tool: echo
        Echo tool.

        ## Parameters
        - text (string, required): Text to echo
        """)
        tool = parse_md_tool(tmp_tools_dir / "echo.md")
        assert tool is not None
        result = await tool.ainvoke({"text": "hello"})
        assert "hello" in result
