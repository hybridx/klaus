"""Shared application state — injected into route handlers."""

from __future__ import annotations

from klaus.agents.graph import klausAgent
from klaus.db import Database
from klaus.events.bus import EventBus
from klaus.mcp.manager import MCPServerManager
from klaus.memory.store import MemoryManager, SqliteStore
from klaus.models.registry import ModelRegistry
from klaus.routing.router import TaskRouter
from klaus.superpowers.registry import SuperpowerRegistry


class AppState:
    """Holds references to the core subsystems, accessible from any route."""

    def __init__(self, prefer_local: bool = True) -> None:
        self.db = Database()
        self.model_registry = ModelRegistry()
        self.mcp_manager = MCPServerManager()
        self.task_router = TaskRouter(prefer_local=prefer_local)
        self.event_bus = EventBus()
        self.memory: MemoryManager = None  # type: ignore[assignment]
        self.superpowers: SuperpowerRegistry | None = None
        self.agent: klausAgent | None = None

    async def init_db(self) -> None:
        await self.db.connect()
        self.memory = MemoryManager(store=SqliteStore(self.db))

    def init_superpowers(self) -> SuperpowerRegistry:
        self.superpowers = SuperpowerRegistry(self.memory)
        return self.superpowers

    def init_agent(self) -> None:
        self.agent = klausAgent(
            self.model_registry,
            self.mcp_manager,
            memory=self.memory,
            superpowers=self.superpowers,
        )


_state: AppState | None = None


def get_state() -> AppState:
    if _state is None:
        raise RuntimeError("AppState not initialized — call init_state() first")
    return _state


def init_state(prefer_local: bool = True) -> AppState:
    global _state
    _state = AppState(prefer_local=prefer_local)
    return _state
