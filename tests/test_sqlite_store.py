"""Tests for SqliteStore memory backend."""

from __future__ import annotations

import pytest
from klaus.db import Database
from klaus.memory.store import MemoryManager, SqliteStore
from klaus.memory.tree import MemoryTree


@pytest.fixture()
async def db(tmp_path):
    d = Database(path=tmp_path / "mem.db")
    await d.connect()
    yield d
    await d.close()


@pytest.mark.asyncio
async def test_sqlite_store_save_load(db: Database):
    store = SqliteStore(db)
    tree = MemoryTree()
    tree.put("/skills/python", "Python programming")
    tree.put("/skills/rust", "Rust systems programming")

    await store.save(tree)
    loaded = await store.load()

    assert loaded is not None
    assert loaded.size == tree.size
    node = loaded.get("/skills/python")
    assert node is not None
    assert node.content == "Python programming"


@pytest.mark.asyncio
async def test_sqlite_store_exists(db: Database):
    store = SqliteStore(db)
    assert await store.exists() is False

    tree = MemoryTree()
    tree.put("/test", "data")
    await store.save(tree)

    assert await store.exists() is True


@pytest.mark.asyncio
async def test_sqlite_store_load_empty(db: Database):
    store = SqliteStore(db)
    assert await store.load() is None


@pytest.mark.asyncio
async def test_memory_manager_with_sqlite(db: Database):
    store = SqliteStore(db)
    mgr = MemoryManager(store=store)

    await mgr.startup()
    assert mgr.tree.size == 4  # root + superpowers + conversations + knowledge

    mgr.put("/data/test", "hello")
    await mgr.save()

    mgr2 = MemoryManager(store=store)
    await mgr2.startup()

    node = mgr2.get("/data/test")
    assert node is not None
    assert node.content == "hello"
