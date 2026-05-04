"""Tests for the superpower system."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.tools import BaseTool, StructuredTool

from klaus.memory.store import JsonFileStore, MemoryManager
from klaus.superpowers.base import Superpower
from klaus.superpowers.registry import SuperpowerRegistry


class DummySuperpower(Superpower):
    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "A test superpower"

    @property
    def tags(self) -> list[str]:
        return ["test"]

    def get_tools(self) -> list[BaseTool]:
        def hello(name: str) -> str:
            return f"Hello, {name}!"

        return [StructuredTool.from_function(hello, name="hello", description="Say hello")]


class NoToolSuperpower(Superpower):
    @property
    def name(self) -> str:
        return "empty"

    @property
    def description(self) -> str:
        return "No tools"

    def get_tools(self) -> list[BaseTool]:
        return []


@pytest.fixture()
async def memory(tmp_path: Path) -> MemoryManager:
    store = JsonFileStore(path=tmp_path / "mem.json")
    mgr = MemoryManager(store=store)
    await mgr.startup()
    return mgr


class TestSuperpower:
    def test_default_state(self):
        sp = DummySuperpower()
        assert sp.is_active is False
        assert sp.memory_path == "/superpowers/dummy"

    async def test_activate_deactivate(self):
        sp = DummySuperpower()
        await sp.activate()
        assert sp.is_active is True
        await sp.deactivate()
        assert sp.is_active is False

    def test_get_tools(self):
        sp = DummySuperpower()
        tools = sp.get_tools()
        assert len(tools) == 1
        assert tools[0].name == "hello"

    def test_status(self):
        sp = DummySuperpower()
        status = sp.get_status()
        assert status["name"] == "dummy"
        assert status["active"] is False
        assert "test" in status["tags"]


class TestSuperpowerRegistry:
    async def test_register(self, memory: MemoryManager):
        registry = SuperpowerRegistry(memory)
        sp = DummySuperpower()
        await registry.register(sp)
        assert registry.active_count == 1
        assert sp.is_active

    async def test_duplicate_register_raises(self, memory: MemoryManager):
        registry = SuperpowerRegistry(memory)
        await registry.register(DummySuperpower())
        with pytest.raises(ValueError, match="already registered"):
            await registry.register(DummySuperpower())

    async def test_unregister(self, memory: MemoryManager):
        registry = SuperpowerRegistry(memory)
        sp = DummySuperpower()
        await registry.register(sp)
        await registry.unregister("dummy")
        assert registry.active_count == 0
        assert not sp.is_active

    async def test_collect_tools(self, memory: MemoryManager):
        registry = SuperpowerRegistry(memory)
        await registry.register(DummySuperpower())
        await registry.register(NoToolSuperpower())
        tools = registry.collect_tools()
        assert len(tools) == 1
        assert tools[0].name == "hello"

    async def test_list_active(self, memory: MemoryManager):
        registry = SuperpowerRegistry(memory)
        await registry.register(DummySuperpower())
        active = registry.list_active()
        assert len(active) == 1
        assert active[0]["name"] == "dummy"

    async def test_get(self, memory: MemoryManager):
        registry = SuperpowerRegistry(memory)
        sp = DummySuperpower()
        await registry.register(sp)
        assert registry.get("dummy") is sp
        assert registry.get("nonexistent") is None

    async def test_writes_to_memory(self, memory: MemoryManager):
        registry = SuperpowerRegistry(memory)
        await registry.register(DummySuperpower())
        node = memory.get("/superpowers/dummy")
        assert node is not None
        assert "test superpower" in node.content.lower()

    async def test_shutdown_all(self, memory: MemoryManager):
        registry = SuperpowerRegistry(memory)
        await registry.register(DummySuperpower())
        await registry.register(NoToolSuperpower())
        await registry.shutdown_all()
        assert registry.active_count == 0
