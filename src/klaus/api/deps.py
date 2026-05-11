"""Shared application state — injected into route handlers."""

from __future__ import annotations

import logging
import os

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection

from klaus.agents.graph import klausAgent
from klaus.db import Database
from klaus.events.bus import EventBus
from klaus.mcp.manager import MCPServerManager
from klaus.memory.store import MemoryManager, PostgresStore
from klaus.models.registry import ModelRegistry
from klaus.routing.router import TaskRouter
from klaus.superpowers.registry import SuperpowerRegistry

logger = logging.getLogger(__name__)

_DEFAULT_PG_URL = "postgresql://klaus:klaus@localhost:5432/klaus"


class AppState:
    """Holds references to the core subsystems, accessible from any route."""

    def __init__(
        self,
        prefer_local: bool = True,
        database_url: str | None = None,
        pool_min: int = 2,
        pool_max: int = 10,
    ) -> None:
        self._database_url = database_url or os.getenv("DATABASE_URL", _DEFAULT_PG_URL)
        self.db = Database(
            url=self._database_url,
            pool_min=pool_min,
            pool_max=pool_max,
        )
        self.model_registry = ModelRegistry()
        self.mcp_manager = MCPServerManager()
        self.task_router = TaskRouter(prefer_local=prefer_local)
        self.event_bus = EventBus()
        self.memory: MemoryManager = None  # type: ignore[assignment]
        self.superpowers: SuperpowerRegistry | None = None
        self.agent: klausAgent | None = None
        self.checkpointer: AsyncPostgresSaver | None = None
        self._checkpoint_conn: AsyncConnection | None = None

    async def init_db(self) -> None:
        await self.db.connect()
        self.memory = MemoryManager(store=PostgresStore(self.db), db=self.db)

    async def init_checkpointer(self) -> AsyncPostgresSaver:
        """Open a dedicated psycopg connection for LangGraph checkpointing."""
        self._checkpoint_conn = await AsyncConnection.connect(
            self._database_url,
            autocommit=True,
            prepare_threshold=0,
        )
        self.checkpointer = AsyncPostgresSaver(conn=self._checkpoint_conn)
        await self.checkpointer.setup()
        logger.info("LangGraph checkpointer ready (PostgreSQL)")
        return self.checkpointer

    async def close_checkpointer(self) -> None:
        if self._checkpoint_conn and not self._checkpoint_conn.closed:
            await self._checkpoint_conn.close()
            self._checkpoint_conn = None
            self.checkpointer = None

    def init_superpowers(self) -> SuperpowerRegistry:
        self.superpowers = SuperpowerRegistry(self.memory)
        return self.superpowers

    def init_agent(self, orchestrator_config: dict | None = None, md_agents=None) -> None:
        self.agent = klausAgent(
            self.model_registry,
            self.mcp_manager,
            memory=self.memory,
            superpowers=self.superpowers,
            db=self.db,
            task_router=self.task_router,
            orchestrator_config=orchestrator_config,
            md_agents=md_agents,
            checkpointer=self.checkpointer,
        )


_state: AppState | None = None


def get_state() -> AppState:
    if _state is None:
        raise RuntimeError("AppState not initialized — call init_state() first")
    return _state


def init_state(
    prefer_local: bool = True,
    database_url: str | None = None,
    pool_min: int = 2,
    pool_max: int = 10,
) -> AppState:
    global _state
    _state = AppState(
        prefer_local=prefer_local,
        database_url=database_url,
        pool_min=pool_min,
        pool_max=pool_max,
    )
    return _state
