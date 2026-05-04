"""Tests for the tree-structured memory system."""

from __future__ import annotations

from klaus.memory.tree import MemoryNode, MemoryTree


class TestMemoryNode:
    def test_default_fields(self):
        node = MemoryNode()
        assert node.name == ""
        assert node.content == ""
        assert node.is_leaf
        assert not node.is_branch
        assert node.child_count == 0
        assert node.subtree_size() == 1

    def test_touch_increments_access(self):
        node = MemoryNode()
        assert node.access_count == 0
        node.touch()
        assert node.access_count == 1

    def test_serialization_roundtrip(self):
        node = MemoryNode(name="test", content="hello", tags=["a", "b"])
        child = MemoryNode(name="child", content="world")
        node.children["child"] = child

        data = node.to_dict()
        restored = MemoryNode.from_dict(data)

        assert restored.name == "test"
        assert restored.content == "hello"
        assert restored.tags == ["a", "b"]
        assert "child" in restored.children
        assert restored.children["child"].content == "world"


class TestMemoryTree:
    def test_default_branches(self, tree: MemoryTree):
        children = tree.ls("/")
        assert "superpowers" in children
        assert "conversations" in children
        assert "knowledge" in children

    def test_put_and_get(self, tree: MemoryTree):
        tree.put("/knowledge/user/name", "Alice")
        node = tree.get("/knowledge/user/name")
        assert node is not None
        assert node.content == "Alice"
        assert node.name == "name"

    def test_get_nonexistent_returns_none(self, tree: MemoryTree):
        assert tree.get("/does/not/exist") is None

    def test_put_creates_intermediates(self, tree: MemoryTree):
        tree.put("/deep/nested/path/here", "value")
        assert tree.exists("/deep")
        assert tree.exists("/deep/nested")
        assert tree.exists("/deep/nested/path")
        assert tree.exists("/deep/nested/path/here")

    def test_put_merge(self, tree: MemoryTree):
        tree.put("/knowledge/fact", "first", tags=["a"])
        tree.put("/knowledge/fact", "second", tags=["b"], merge=True)
        node = tree.get("/knowledge/fact")
        assert node is not None
        assert "first" in node.content
        assert "second" in node.content
        assert "a" in node.tags
        assert "b" in node.tags

    def test_put_overwrite(self, tree: MemoryTree):
        tree.put("/knowledge/fact", "old")
        tree.put("/knowledge/fact", "new")
        node = tree.get("/knowledge/fact")
        assert node is not None
        assert node.content == "new"

    def test_delete(self, tree: MemoryTree):
        tree.put("/knowledge/temp", "delete me")
        assert tree.delete("/knowledge/temp") is True
        assert tree.get("/knowledge/temp") is None

    def test_delete_nonexistent(self, tree: MemoryTree):
        assert tree.delete("/nope") is False

    def test_delete_root_returns_false(self, tree: MemoryTree):
        assert tree.delete("") is False

    def test_move(self, tree: MemoryTree):
        tree.put("/knowledge/old_spot", "moving")
        assert tree.move("/knowledge/old_spot", "/knowledge/new_spot") is True
        assert tree.get("/knowledge/old_spot") is None
        node = tree.get("/knowledge/new_spot")
        assert node is not None
        assert node.content == "moving"

    def test_move_nonexistent_returns_false(self, tree: MemoryTree):
        assert tree.move("/nope", "/somewhere") is False

    def test_ls(self, tree: MemoryTree):
        tree.put("/knowledge/a", "1")
        tree.put("/knowledge/b", "2")
        children = tree.ls("/knowledge")
        assert "a" in children
        assert "b" in children

    def test_ls_empty(self, tree: MemoryTree):
        assert tree.ls("/nonexistent") == []

    def test_walk(self, tree: MemoryTree):
        tree.put("/knowledge/x", "x_val")
        tree.put("/knowledge/x/y", "y_val")
        walked = tree.walk("/knowledge/x")
        paths = [p for p, _ in walked]
        assert "/knowledge/x" in paths
        assert "/knowledge/x/y" in paths

    def test_search(self, tree: MemoryTree):
        tree.put("/knowledge/facts/python", "Python is a programming language")
        tree.put("/knowledge/facts/rust", "Rust is a systems language")
        results = tree.search("python")
        assert len(results) >= 1
        assert any("python" in path.lower() for path, _, _ in results)

    def test_search_no_results(self, tree: MemoryTree):
        results = tree.search("zzz_nonexistent_term_zzz")
        assert results == []

    def test_recent(self, tree: MemoryTree):
        tree.put("/knowledge/old", "old content")
        tree.put("/knowledge/new", "new content")
        recent = tree.recent("/knowledge", n=1)
        assert len(recent) == 1

    def test_context_for(self, tree: MemoryTree):
        tree.put("/knowledge/user/name", "Alice")
        tree.put("/knowledge/user/age", "30")
        context = tree.context_for("/knowledge/user/name")
        assert len(context) > 0

    def test_serialization_roundtrip(self, tree: MemoryTree):
        tree.put("/knowledge/user/name", "Bob", tags=["user"])
        tree.put("/knowledge/facts/pi", "3.14", metadata={"type": "math"})

        data = tree.to_dict()
        restored = MemoryTree.from_dict(data)

        node = restored.get("/knowledge/user/name")
        assert node is not None
        assert node.content == "Bob"
        assert "user" in node.tags

        pi = restored.get("/knowledge/facts/pi")
        assert pi is not None
        assert pi.content == "3.14"

    def test_size(self, tree: MemoryTree):
        initial = tree.size
        tree.put("/knowledge/a", "a")
        assert tree.size == initial + 1
