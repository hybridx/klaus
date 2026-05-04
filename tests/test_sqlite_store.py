"""Tests for PostgresStore memory backend.

These tests require a running PostgreSQL instance.
Start one with: podman-compose up postgres
"""

from __future__ import annotations

import os

import pytest

from klaus.db import Database
from klaus.memory.store import MemoryManager, PostgresStore
from klaus.memory.tree import MemoryTree

_TEST_URL = os.getenv(
    "DATABASE_URL", "postgresql://klaus:klaus@localhost:5432/klaus"
)

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_PG_TESTS", "0") == "1",
    reason="PostgreSQL not available (set SKIP_PG_TESTS=0 to enable)",
)


@pytest.fixture()
async def db():
    d = Database(url=_TEST_URL)
    await d.connect()
    await d.pool.execute("DELETE FROM memory_tree WHERE id = 1")
    yield d
    await d.close()


@pytest.mark.asyncio
async def test_postgres_store_save_load(db: Database):
    store = PostgresStore(db)
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
async def test_postgres_store_exists(db: Database):
    store = PostgresStore(db)
    assert await store.exists() is False

    tree = MemoryTree()
    tree.put("/test", "data")
    await store.save(tree)

    assert await store.exists() is True


@pytest.mark.asyncio
async def test_postgres_store_load_empty(db: Database):
    store = PostgresStore(db)
    assert await store.load() is None


@pytest.mark.asyncio
async def test_memory_manager_with_postgres(db: Database):
    store = PostgresStore(db)
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
