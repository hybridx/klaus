"""Persistence backend for the memory tree.

Supports JSON file (legacy), SQLite, and PostgreSQL (default). The interface is
deliberately simple so it can be swapped without touching callers.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from klaus.memory.tree import MemoryTree

if TYPE_CHECKING:
    from klaus.db import Database

logger = logging.getLogger(__name__)


class MemoryStoreBackend(ABC):
    """Interface for memory persistence backends."""

    @abstractmethod
    async def save(self, tree: MemoryTree) -> None: ...

    @abstractmethod
    async def load(self) -> MemoryTree | None: ...

    @abstractmethod
    async def exists(self) -> bool: ...


class JsonFileStore(MemoryStoreBackend):
    """Persist the memory tree as a single JSON file.

    Good for local dev and single-node deployments. For multi-cluster,
    swap this for a shared store (Redis, Postgres, etc.).
    """

    def __init__(self, path: str | Path = "data/memory.json") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def save(self, tree: MemoryTree) -> None:
        tmp = self._path.with_suffix(".tmp")
        data = {
            "version": 1,
            "saved_at": time.time(),
            "tree": tree.to_dict(),
        }
        tmp.write_text(json.dumps(data, indent=2))
        shutil.move(str(tmp), str(self._path))
        logger.debug("Memory saved (%d nodes) to %s", tree.size, self._path)

    async def load(self) -> MemoryTree | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text())
            tree = MemoryTree.from_dict(data["tree"])
            logger.info(
                "Memory loaded (%d nodes) from %s", tree.size, self._path
            )
            return tree
        except Exception as exc:
            logger.error("Failed to load memory from %s: %s", self._path, exc)
            return None

    async def exists(self) -> bool:
        return self._path.exists()


class SqliteStore(MemoryStoreBackend):
    """Persist the memory tree in SQLite.

    The tree is serialized as a single JSON blob in the memory_tree table.
    This keeps the tree's hierarchical structure intact while getting
    SQLite's durability, WAL mode, and crash safety.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(self, tree: MemoryTree) -> None:
        await self._db.save_memory_tree(tree.to_dict())
        logger.debug("Memory saved (%d nodes) to SQLite", tree.size)

    async def load(self) -> MemoryTree | None:
        data = await self._db.load_memory_tree()
        if data is None:
            return None
        try:
            tree = MemoryTree.from_dict(data)
            logger.info("Memory loaded (%d nodes) from SQLite", tree.size)
            return tree
        except Exception as exc:
            logger.error("Failed to load memory from SQLite: %s", exc)
            return None

    async def exists(self) -> bool:
        return await self._db.load_memory_tree() is not None


class PostgresStore(MemoryStoreBackend):
    """Persist the memory tree in PostgreSQL.

    Same serialization approach as SqliteStore (JSON blob), but
    backed by asyncpg pool for better concurrency and durability.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(self, tree: MemoryTree) -> None:
        await self._db.save_memory_tree(tree.to_dict())
        logger.debug("Memory saved (%d nodes) to PostgreSQL", tree.size)

    async def load(self) -> MemoryTree | None:
        data = await self._db.load_memory_tree()
        if data is None:
            return None
        try:
            tree = MemoryTree.from_dict(data)
            logger.info("Memory loaded (%d nodes) from PostgreSQL", tree.size)
            return tree
        except Exception as exc:
            logger.error("Failed to load memory from PostgreSQL: %s", exc)
            return None

    async def exists(self) -> bool:
        return await self._db.load_memory_tree() is not None


class MemoryManager:
    """Owns the memory tree and handles persistence lifecycle.

    Use this instead of touching the tree or store directly.
    """

    def __init__(
        self,
        store: MemoryStoreBackend | None = None,
        auto_save_interval: float = 60.0,
        db=None,
    ) -> None:
        self._store = store or JsonFileStore()
        self._auto_save_interval = auto_save_interval
        self._last_save: float = 0
        self._dirty = False
        self._db = db
        self._pending_embeddings: list[tuple[str, str]] = []
        self.tree = MemoryTree()

    async def startup(self) -> None:
        """Load persisted memory (if any) on startup."""
        existing = await self._store.load()
        if existing:
            self.tree = existing
        logger.info("Memory tree ready (%d nodes)", self.tree.size)

    async def shutdown(self) -> None:
        """Persist memory on shutdown."""
        await self.flush_embeddings()
        await self.save()

    def mark_dirty(self) -> None:
        self._dirty = True

    async def save(self) -> None:
        await self._store.save(self.tree)
        self._last_save = time.time()
        self._dirty = False

    async def maybe_save(self) -> None:
        """Auto-save if enough time has passed since last save."""
        if self._dirty and (time.time() - self._last_save) > self._auto_save_interval:
            await self.save()
        await self.flush_embeddings()

    async def flush_embeddings(self) -> None:
        """Index pending embeddings into pgvector."""
        if not self._db or not self._pending_embeddings:
            return
        batch = self._pending_embeddings[:]
        self._pending_embeddings.clear()
        try:
            from klaus.memory.index import MemoryIndex
            index = MemoryIndex(self.tree, db=self._db)
            for path, content in batch:
                await index.index_node(path, content)
        except Exception as exc:
            logger.warning("Failed to index embeddings: %s", exc)

    def put(self, path: str, content: str = "", **kwargs) -> None:
        """Write to the tree, mark dirty, and queue for embedding."""
        self.tree.put(path, content, **kwargs)
        self.mark_dirty()
        if content.strip() and (
            path.startswith("/knowledge") or path.startswith("/user")
        ):
            self._pending_embeddings.append((path, content))

    def get(self, path: str):
        return self.tree.get(path)

    def delete(self, path: str) -> bool:
        result = self.tree.delete(path)
        if result:
            self.mark_dirty()
        return result

    def search(self, query: str, root_path: str = "/", **kwargs):
        return self.tree.search(query, root_path, **kwargs)

    def ls(self, path: str = "/") -> list[str]:
        return self.tree.ls(path)

    def context_for(self, path: str, depth: int = 2):
        return self.tree.context_for(path, depth)
