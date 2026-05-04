"""Tree-structured memory — the core data structure of klaus.

The memory tree is a hierarchical store where every piece of knowledge,
conversation, superpower registration, and learned fact lives as a node.
Related information clusters naturally on the same branch, making retrieval
fast — you walk from root toward the relevant subtree instead of scanning
everything.

Layout convention:
    /superpowers/         registered capabilities
    /conversations/       conversation history (one branch per session)
    /knowledge/           persistent learned facts
    /knowledge/user/      user preferences and patterns
    /knowledge/system/    system state snapshots

Nodes are addressed by slash-separated paths, like a filesystem.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryNode:
    """Single node in the memory tree.

    A node can be a branch (has children) and a leaf (has content) at the
    same time — like a directory that also holds data.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    children: dict[str, MemoryNode] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0

    # Optional embedding for semantic search (populated lazily)
    embedding: list[float] | None = field(default=None, repr=False)

    def touch(self) -> None:
        self.access_count += 1
        self.updated_at = time.time()

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    @property
    def is_branch(self) -> bool:
        return len(self.children) > 0

    @property
    def child_count(self) -> int:
        return len(self.children)

    def subtree_size(self) -> int:
        """Total node count in this subtree (including self)."""
        return 1 + sum(c.subtree_size() for c in self.children.values())

    def to_dict(self) -> dict:
        """Serialize the full subtree (for persistence)."""
        return {
            "id": self.id,
            "name": self.name,
            "content": self.content,
            "metadata": self.metadata,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "access_count": self.access_count,
            "children": {k: v.to_dict() for k, v in self.children.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> MemoryNode:
        """Reconstruct a subtree from serialized data."""
        children = {
            k: cls.from_dict(v) for k, v in data.get("children", {}).items()
        }
        return cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            name=data.get("name", ""),
            content=data.get("content", ""),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            children=children,
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            access_count=data.get("access_count", 0),
        )


def _split_path(path: str) -> list[str]:
    """Split a slash-separated path into segments, ignoring empty parts."""
    return [p for p in path.strip("/").split("/") if p]


class MemoryTree:
    """Hierarchical memory store with path-based access.

    Paths work like a filesystem:
        tree.put("/knowledge/user/name", "Alice")
        tree.get("/knowledge/user/name").content  →  "Alice"
        tree.ls("/knowledge")  →  ["user"]
        tree.search("/knowledge", "name")  →  matching nodes

    The tree auto-creates intermediate nodes (like `mkdir -p`).
    """

    def __init__(self) -> None:
        self.root = MemoryNode(name="root")
        self._init_structure()

    def _init_structure(self) -> None:
        """Create the top-level branches."""
        for branch in ("superpowers", "conversations", "knowledge"):
            if branch not in self.root.children:
                self.root.children[branch] = MemoryNode(name=branch)

    # ── Navigation ───────────────────────────────────────────

    def _walk(self, path: str, create: bool = False) -> MemoryNode | None:
        """Walk to a node by path. If create=True, make intermediate nodes."""
        segments = _split_path(path)
        node = self.root
        for seg in segments:
            if seg in node.children:
                node = node.children[seg]
            elif create:
                child = MemoryNode(name=seg)
                node.children[seg] = child
                node = child
            else:
                return None
        return node

    def get(self, path: str) -> MemoryNode | None:
        """Get a node by path. Returns None if not found."""
        node = self._walk(path)
        if node:
            node.touch()
        return node

    def exists(self, path: str) -> bool:
        return self._walk(path) is not None

    # ── Mutation ─────────────────────────────────────────────

    def put(
        self,
        path: str,
        content: str = "",
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        merge: bool = False,
    ) -> MemoryNode:
        """Create or update a node at the given path.

        Intermediate nodes are auto-created. If merge=True and the node
        already exists, content is appended and metadata is merged.
        """
        node = self._walk(path, create=True)
        assert node is not None

        if merge and node.content:
            node.content += "\n" + content
            node.metadata.update(metadata or {})
            node.tags = list(set(node.tags + (tags or [])))
        else:
            node.content = content
            if metadata:
                node.metadata = metadata
            if tags:
                node.tags = tags

        node.updated_at = time.time()
        node.embedding = None  # invalidate cached embedding
        return node

    def delete(self, path: str) -> bool:
        """Remove a node and its entire subtree. Returns True if it existed."""
        segments = _split_path(path)
        if not segments:
            return False

        parent = self._walk("/".join(segments[:-1]))
        if parent is None:
            return False

        target = segments[-1]
        if target in parent.children:
            del parent.children[target]
            return True
        return False

    def move(self, src: str, dst: str) -> bool:
        """Move a subtree from src to dst."""
        src_segments = _split_path(src)
        if not src_segments:
            return False

        src_parent = self._walk("/".join(src_segments[:-1]))
        if src_parent is None or src_segments[-1] not in src_parent.children:
            return False

        node = src_parent.children.pop(src_segments[-1])

        dst_segments = _split_path(dst)
        dst_parent = self._walk("/".join(dst_segments[:-1]), create=True)
        assert dst_parent is not None
        node.name = dst_segments[-1]
        dst_parent.children[dst_segments[-1]] = node
        return True

    # ── Query ────────────────────────────────────────────────

    def ls(self, path: str = "/") -> list[str]:
        """List immediate children of a node."""
        node = self._walk(path)
        if node is None:
            return []
        return list(node.children.keys())

    def walk(self, path: str = "/") -> list[tuple[str, MemoryNode]]:
        """Recursively walk the subtree, yielding (full_path, node) pairs."""
        node = self._walk(path)
        if node is None:
            return []

        results: list[tuple[str, MemoryNode]] = []
        prefix = path.rstrip("/")

        def _recurse(n: MemoryNode, p: str) -> None:
            results.append((p, n))
            for name, child in n.children.items():
                _recurse(child, f"{p}/{name}")

        _recurse(node, prefix)
        return results

    def search(
        self,
        query: str,
        root_path: str = "/",
        max_results: int = 20,
    ) -> list[tuple[str, MemoryNode, float]]:
        """Keyword search across the subtree.

        Returns (path, node, score) sorted by relevance.
        Score is a simple TF-based match — semantic search is in index.py.
        """
        query_lower = query.lower()
        terms = query_lower.split()
        results: list[tuple[str, MemoryNode, float]] = []

        for path, node in self.walk(root_path):
            score = 0.0
            searchable = f"{node.name} {node.content} {' '.join(node.tags)}".lower()
            for term in terms:
                if term in searchable:
                    score += searchable.count(term)
            if term in node.name.lower():
                score *= 2.0  # boost name matches
            if score > 0:
                results.append((path, node, score))

        results.sort(key=lambda x: x[2], reverse=True)
        return results[:max_results]

    def recent(
        self,
        root_path: str = "/",
        n: int = 10,
    ) -> list[tuple[str, MemoryNode]]:
        """Return the N most recently updated nodes under a path."""
        all_nodes = self.walk(root_path)
        all_nodes.sort(key=lambda x: x[1].updated_at, reverse=True)
        return all_nodes[:n]

    def context_for(self, path: str, depth: int = 2) -> list[MemoryNode]:
        """Gather context: the node itself, its ancestors, and nearby siblings.

        This is what gets injected into the agent as memory context —
        the relevant branch of the tree.
        """
        segments = _split_path(path)
        context: list[MemoryNode] = []

        # Ancestors (walk down from root)
        current = self.root
        for seg in segments:
            if seg in current.children:
                current = current.children[seg]
                context.append(current)

        # Siblings of the target (nearby related info)
        if len(segments) >= 2:
            parent = self._walk("/".join(segments[:-1]))
            if parent:
                for name, child in parent.children.items():
                    if name != segments[-1] and child not in context:
                        context.append(child)
                        if depth > 1:
                            for grandchild in child.children.values():
                                context.append(grandchild)

        return context

    # ── Serialization ────────────────────────────────────────

    def to_dict(self) -> dict:
        return self.root.to_dict()

    @classmethod
    def from_dict(cls, data: dict) -> MemoryTree:
        tree = cls.__new__(cls)
        tree.root = MemoryNode.from_dict(data)
        tree._init_structure()
        return tree

    @property
    def size(self) -> int:
        return self.root.subtree_size()
