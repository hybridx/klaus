"""SQLite database — single embedded DB for all klaus persistence.

Tables:
    memory_tree   — serialized memory tree (single-row, JSON blob)
    conversations — full message history per session
    routing_rules — task routing rules (survive restarts)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_tree (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    data     TEXT    NOT NULL,
    saved_at REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    model      TEXT,
    backend    TEXT,
    created_at REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);

CREATE TABLE IF NOT EXISTS routing_rules (
    task     TEXT PRIMARY KEY,
    rule     TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


class Database:
    """Async SQLite connection manager."""

    def __init__(self, path: str | Path = "data/klaus.db") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(str(self._path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.commit()
        logger.info("SQLite database ready at %s", self._path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected — call connect() first")
        return self._db

    # ── Memory tree ──────────────────────────────────────────

    async def save_memory_tree(self, tree_data: dict) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO memory_tree (id, data, saved_at) VALUES (1, ?, ?)",
            (json.dumps(tree_data), time.time()),
        )
        await self.conn.commit()

    async def load_memory_tree(self) -> dict | None:
        async with self.conn.execute("SELECT data FROM memory_tree WHERE id = 1") as cur:
            row = await cur.fetchone()
        if row:
            return json.loads(row[0])
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
        await self.conn.execute(
            "INSERT INTO conversations (session_id, role, content, model, backend, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, model, backend, time.time()),
        )
        await self.conn.commit()

    async def get_conversation(
        self, session_id: str, limit: int = 50
    ) -> list[dict]:
        async with self.conn.execute(
            "SELECT role, content, model, backend, created_at "
            "FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "role": r[0],
                "content": r[1],
                "model": r[2],
                "backend": r[3],
                "created_at": r[4],
            }
            for r in reversed(rows)
        ]

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        async with self.conn.execute(
            "SELECT session_id, COUNT(*) as msg_count, MAX(created_at) as last_at "
            "FROM conversations GROUP BY session_id ORDER BY last_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {"session_id": r[0], "message_count": r[1], "last_active": r[2]}
            for r in rows
        ]

    # ── Routing rules ────────────────────────────────────────

    async def save_routing_rule(self, task: str, rule: dict) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO routing_rules (task, rule, updated_at) VALUES (?, ?, ?)",
            (task, json.dumps(rule), time.time()),
        )
        await self.conn.commit()

    async def delete_routing_rule(self, task: str) -> None:
        await self.conn.execute("DELETE FROM routing_rules WHERE task = ?", (task,))
        await self.conn.commit()

    async def load_routing_rules(self) -> dict[str, dict]:
        async with self.conn.execute("SELECT task, rule FROM routing_rules") as cur:
            rows = await cur.fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}
