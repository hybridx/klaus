"""Tests for the PostgreSQL database layer.

These tests require a running PostgreSQL instance with pgvector.
Start one with: podman-compose up postgres

Set DATABASE_URL or use the default: postgresql://klaus:klaus@localhost:5432/klaus
"""

from __future__ import annotations

import os

import pytest

from klaus.db import Database

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
    # Clean up test data before each test
    await d.pool.execute("DELETE FROM conversations")
    await d.pool.execute("DELETE FROM routing_rules")
    await d.pool.execute("DELETE FROM memory_tree WHERE id = 1")
    await d.pool.execute("DELETE FROM embeddings")
    yield d
    await d.close()


# ── Memory tree ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_tree_roundtrip(db: Database):
    tree_data = {"root": {"children": {"a": {"content": "hello"}}}}
    await db.save_memory_tree(tree_data)
    loaded = await db.load_memory_tree()
    assert loaded == tree_data


@pytest.mark.asyncio
async def test_memory_tree_overwrite(db: Database):
    await db.save_memory_tree({"v": 1})
    await db.save_memory_tree({"v": 2})
    loaded = await db.load_memory_tree()
    assert loaded == {"v": 2}


@pytest.mark.asyncio
async def test_memory_tree_empty(db: Database):
    assert await db.load_memory_tree() is None


# ── Conversations ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_get_conversation(db: Database):
    await db.save_message("sess1", "user", "Hello")
    await db.save_message(
        "sess1", "assistant", "Hi there",
        model="llama3.2", backend="ollama",
    )

    messages = await db.get_conversation("sess1")
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["model"] == "llama3.2"


@pytest.mark.asyncio
async def test_conversation_limit(db: Database):
    for i in range(10):
        await db.save_message("sess2", "user", f"msg {i}")
    messages = await db.get_conversation("sess2", limit=3)
    assert len(messages) == 3
    assert messages[-1]["content"] == "msg 9"


@pytest.mark.asyncio
async def test_list_sessions(db: Database):
    await db.save_message("alpha", "user", "a")
    await db.save_message("beta", "user", "b")
    await db.save_message("alpha", "user", "c")

    sessions = await db.list_sessions()
    assert len(sessions) == 2
    names = [s["session_id"] for s in sessions]
    assert "alpha" in names
    assert "beta" in names
    alpha = next(s for s in sessions if s["session_id"] == "alpha")
    assert alpha["message_count"] == 2


@pytest.mark.asyncio
async def test_empty_conversation(db: Database):
    messages = await db.get_conversation("nonexistent")
    assert messages == []


@pytest.mark.asyncio
async def test_delete_all_conversations(db: Database):
    await db.save_message("s1", "user", "hi")
    await db.save_message("s2", "user", "bye")
    count = await db.delete_all_conversations()
    assert count == 2
    assert await db.list_sessions() == []


# ── Routing rules ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_routing_rules_roundtrip(db: Database):
    rule = {
        "preferred_backend": "ollama",
        "preferred_model": "llama3.2",
        "fallback_backends": [],
    }
    await db.save_routing_rule("coding", rule)

    rules = await db.load_routing_rules()
    assert "coding" in rules
    assert rules["coding"]["preferred_model"] == "llama3.2"


@pytest.mark.asyncio
async def test_routing_rules_update(db: Database):
    await db.save_routing_rule("chat", {"preferred_backend": "ollama"})
    await db.save_routing_rule("chat", {"preferred_backend": "gemini"})

    rules = await db.load_routing_rules()
    assert rules["chat"]["preferred_backend"] == "gemini"


@pytest.mark.asyncio
async def test_routing_rules_delete(db: Database):
    await db.save_routing_rule("temp", {"preferred_backend": "ollama"})
    await db.delete_routing_rule("temp")

    rules = await db.load_routing_rules()
    assert "temp" not in rules


@pytest.mark.asyncio
async def test_routing_rules_empty(db: Database):
    rules = await db.load_routing_rules()
    assert rules == {}


# ── Embeddings ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_search_embedding(db: Database):
    vec = [0.1] * 384
    await db.save_embedding("/knowledge/test", "test content", vec)

    results = await db.search_embeddings(vec, limit=5)
    assert len(results) >= 1
    assert results[0]["path"] == "/knowledge/test"
    assert results[0]["similarity"] > 0.99


@pytest.mark.asyncio
async def test_embedding_upsert(db: Database):
    vec = [0.2] * 384
    await db.save_embedding("/knowledge/x", "v1", vec)
    await db.save_embedding("/knowledge/x", "v2", vec)

    count = await db.embedding_count()
    assert count == 1


@pytest.mark.asyncio
async def test_delete_embeddings(db: Database):
    vec = [0.3] * 384
    await db.save_embedding("/knowledge/del/a", "a", vec)
    await db.save_embedding("/knowledge/del/b", "b", vec)

    await db.delete_embeddings("/knowledge/del")
    count = await db.embedding_count()
    assert count == 0
