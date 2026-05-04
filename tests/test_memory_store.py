"""Tests for memory persistence."""

from __future__ import annotations

from pathlib import Path

from klaus.memory.store import JsonFileStore, MemoryManager
from klaus.memory.tree import MemoryTree


class TestJsonFileStore:
    async def test_save_and_load(self, tmp_path: Path):
        store = JsonFileStore(path=tmp_path / "mem.json")
        tree = MemoryTree()
        tree.put("/knowledge/test", "saved value")

        await store.save(tree)
        assert await store.exists()

        loaded = await store.load()
        assert loaded is not None
        node = loaded.get("/knowledge/test")
        assert node is not None
        assert node.content == "saved value"

    async def test_load_nonexistent(self, tmp_path: Path):
        store = JsonFileStore(path=tmp_path / "nope.json")
        assert await store.exists() is False
        assert await store.load() is None


class TestMemoryManager:
    async def test_startup_creates_tree(self, tmp_path: Path):
        store = JsonFileStore(path=tmp_path / "mem.json")
        mgr = MemoryManager(store=store)
        await mgr.startup()
        assert mgr.tree.size > 0

    async def test_put_marks_dirty(self, tmp_path: Path):
        store = JsonFileStore(path=tmp_path / "mem.json")
        mgr = MemoryManager(store=store)
        await mgr.startup()
        mgr.put("/knowledge/flag", "dirty test")
        assert mgr._dirty is True

    async def test_save_clears_dirty(self, tmp_path: Path):
        store = JsonFileStore(path=tmp_path / "mem.json")
        mgr = MemoryManager(store=store)
        await mgr.startup()
        mgr.put("/knowledge/x", "val")
        await mgr.save()
        assert mgr._dirty is False

    async def test_delete(self, tmp_path: Path):
        store = JsonFileStore(path=tmp_path / "mem.json")
        mgr = MemoryManager(store=store)
        await mgr.startup()
        mgr.put("/knowledge/temp", "remove me")
        assert mgr.delete("/knowledge/temp") is True
        assert mgr.get("/knowledge/temp") is None

    async def test_shutdown_saves(self, tmp_path: Path):
        store = JsonFileStore(path=tmp_path / "mem.json")
        mgr = MemoryManager(store=store)
        await mgr.startup()
        mgr.put("/knowledge/persist", "keep me")
        await mgr.shutdown()

        mgr2 = MemoryManager(store=store)
        await mgr2.startup()
        node = mgr2.get("/knowledge/persist")
        assert node is not None
        assert node.content == "keep me"
