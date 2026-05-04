"""Tests for the memory index search engine."""

from __future__ import annotations

from klaus.memory.index import MemoryIndex
from klaus.memory.tree import MemoryTree


class TestMemoryIndex:
    def _make_tree(self) -> MemoryTree:
        tree = MemoryTree()
        tree.put("/knowledge/python", "Python is a programming language", tags=["lang"])
        tree.put("/knowledge/rust", "Rust is a systems language", tags=["lang"])
        tree.put("/knowledge/user/name", "Alice", tags=["user", "identity"])
        return tree

    def test_keyword_search(self):
        tree = self._make_tree()
        idx = MemoryIndex(tree)
        results = idx.search("python")
        assert len(results) >= 1
        assert any("python" in r.path.lower() for r in results)

    def test_tag_filter(self):
        tree = self._make_tree()
        idx = MemoryIndex(tree)
        results = idx.search("language", tags=["lang"])
        assert len(results) >= 1
        for r in results:
            assert "tag" in r.match_reason or "keyword" in r.match_reason

    def test_no_results(self):
        tree = self._make_tree()
        idx = MemoryIndex(tree)
        results = idx.search("zzz_nothing_matches_zzz")
        assert results == []

    async def test_gather_context(self):
        tree = self._make_tree()
        idx = MemoryIndex(tree)
        ctx = await idx.gather_context("python programming")
        assert isinstance(ctx, str)

    async def test_gather_context_with_conversation(self):
        tree = self._make_tree()
        tree.put("/conversations/s1", "hello world", tags=["conv"])
        idx = MemoryIndex(tree)
        ctx = await idx.gather_context("hello", conversation_path="/conversations/s1")
        assert isinstance(ctx, str)
