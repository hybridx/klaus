"""PostgreSQL database — asyncpg pool with pgvector for embeddings.

Tables:
    memory_tree   — serialized memory tree (single-row, JSONB blob)
    conversations — full message history per session
    routing_rules — task routing rules (survive restarts)
    embeddings    — vector embeddings for semantic memory search (pgvector)
"""

from __future__ import annotations

import json
import logging
import os
import time

import asyncpg

logger = logging.getLogger(__name__)

_DEFAULT_URL = "postgresql://klaus:klaus@localhost:5432/klaus"

_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memory_tree (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    data     JSONB   NOT NULL,
    saved_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id         SERIAL PRIMARY KEY,
    session_id TEXT    NOT NULL,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    model      TEXT,
    backend    TEXT,
    created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);

CREATE TABLE IF NOT EXISTS routing_rules (
    task       TEXT PRIMARY KEY,
    rule       JSONB NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS embeddings (
    id         SERIAL PRIMARY KEY,
    path       TEXT NOT NULL,
    content    TEXT NOT NULL,
    embedding  vector(768) NOT NULL,
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
);
CREATE INDEX IF NOT EXISTS idx_embed_path ON embeddings(path);
"""


class Database:
    """Async PostgreSQL connection pool manager."""

    def __init__(
        self,
        url: str | None = None,
        pool_min: int = 2,
        pool_max: int = 10,
    ) -> None:
        self._url = url or os.getenv("DATABASE_URL", _DEFAULT_URL)
        self._pool_min = pool_min
        self._pool_max = pool_max
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            self._url,
            min_size=self._pool_min,
            max_size=self._pool_max,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(_SCHEMA)
            await self._migrate_embedding_dimensions(conn)
        logger.info("PostgreSQL ready at %s", self._url.split("@")[-1])

    @staticmethod
    async def _migrate_embedding_dimensions(conn) -> None:
        """Migrate embeddings table from 384-dim to 768-dim if needed."""
        try:
            row = await conn.fetchrow(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'embeddings'::regclass AND attname = 'embedding'"
            )
            if row and row["atttypmod"] != 768:
                logger.info(
                    "Migrating embeddings: %d → 768 dims...",
                    row["atttypmod"],
                )
                await conn.execute("TRUNCATE embeddings")
                await conn.execute("ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(768)")
                logger.info("Embedding migration complete (old data cleared — will re-index)")
        except Exception:
            pass

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database not connected — call connect() first")
        return self._pool

    # ── Memory tree ──────────────────────────────────────────

    async def save_memory_tree(self, tree_data: dict) -> None:
        await self.pool.execute(
            """
            INSERT INTO memory_tree (id, data, saved_at) VALUES (1, $1, $2)
            ON CONFLICT (id) DO UPDATE SET data = $1, saved_at = $2
            """,
            json.dumps(tree_data),
            time.time(),
        )

    async def load_memory_tree(self) -> dict | None:
        row = await self.pool.fetchrow(
            "SELECT data FROM memory_tree WHERE id = 1"
        )
        if row:
            data = row["data"]
            return json.loads(data) if isinstance(data, str) else data
        return None

    # ── Conversations ────────────────────────────────────────

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        model: str | None = None,
        backend: str | None = None,
    ) -> None:
        await self.pool.execute(
            "INSERT INTO conversations "
            "(session_id, role, content, model, backend, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            session_id, role, content, model, backend, time.time(),
        )

    async def get_conversation(
        self, session_id: str, limit: int = 50
    ) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT role, content, model, backend, created_at "
            "FROM conversations WHERE session_id = $1 "
            "ORDER BY id DESC LIMIT $2",
            session_id, limit,
        )
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "model": r["model"],
                "backend": r["backend"],
                "created_at": r["created_at"],
            }
            for r in reversed(rows)
        ]

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT session_id, COUNT(*) as msg_count, "
            "MAX(created_at) as last_at "
            "FROM conversations GROUP BY session_id "
            "ORDER BY last_at DESC LIMIT $1",
            limit,
        )
        return [
            {
                "session_id": r["session_id"],
                "message_count": r["msg_count"],
                "last_active": r["last_at"],
            }
            for r in rows
        ]

    async def delete_all_conversations(self) -> int:
        row = await self.pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM conversations"
        )
        count = row["cnt"] if row else 0
        await self.pool.execute("DELETE FROM conversations")
        return count

    # ── Routing rules ────────────────────────────────────────

    async def save_routing_rule(self, task: str, rule: dict) -> None:
        await self.pool.execute(
            """
            INSERT INTO routing_rules (task, rule, updated_at) VALUES ($1, $2, $3)
            ON CONFLICT (task) DO UPDATE SET rule = $2, updated_at = $3
            """,
            task, json.dumps(rule), time.time(),
        )

    async def delete_routing_rule(self, task: str) -> None:
        await self.pool.execute(
            "DELETE FROM routing_rules WHERE task = $1", task
        )

    async def load_routing_rules(self) -> dict[str, dict]:
        rows = await self.pool.fetch("SELECT task, rule FROM routing_rules")
        result = {}
        for r in rows:
            rule = r["rule"]
            result[r["task"]] = json.loads(rule) if isinstance(rule, str) else rule
        return result

    # ── Embeddings (pgvector) ────────────────────────────────

    async def save_embedding(
        self,
        path: str,
        content: str,
        embedding: list[float],
    ) -> None:
        """Upsert an embedding vector for a memory node."""
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        await self.pool.execute(
            "DELETE FROM embeddings WHERE path = $1", path
        )
        await self.pool.execute(
            "INSERT INTO embeddings (path, content, embedding, created_at) "
            "VALUES ($1, $2, $3, $4)",
            path, content, vec_str, time.time(),
        )

    async def search_embeddings(
        self,
        query_embedding: list[float],
        limit: int = 10,
    ) -> list[dict]:
        """Find nearest neighbors by cosine distance."""
        vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        rows = await self.pool.fetch(
            "SELECT path, content, "
            "1 - (embedding <=> $1::vector) as similarity "
            "FROM embeddings "
            "ORDER BY embedding <=> $1::vector "
            "LIMIT $2",
            vec_str, limit,
        )
        return [
            {
                "path": r["path"],
                "content": r["content"],
                "similarity": float(r["similarity"]),
            }
            for r in rows
        ]

    async def delete_embeddings(self, path: str) -> None:
        """Delete embeddings for a given path (or path prefix)."""
        await self.pool.execute(
            "DELETE FROM embeddings WHERE path LIKE $1",
            path + "%",
        )

    async def embedding_count(self) -> int:
        row = await self.pool.fetchrow("SELECT COUNT(*) as cnt FROM embeddings")
        return row["cnt"] if row else 0
