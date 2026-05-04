"""Superpower — the base class for every klaus capability.

A superpower is any discrete ability that klaus can learn or gain:
- A new MCP server connection
- A new model backend
- A code analysis tool
- A web search capability
- A document reader
- A custom agent skill

Each superpower:
1. Registers itself in the memory tree at /superpowers/{name}
2. Can read/write to its own memory branch
3. Exposes LangChain tools that the agent can use
4. Has a lifecycle (activate → use → deactivate)

To add a new superpower, subclass this and implement the abstract methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from klaus.memory.store import MemoryManager


class Superpower(ABC):
    """Base class for all klaus capabilities."""

    def __init__(self) -> None:
        self._memory: MemoryManager | None = None
        self._active = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier, used as the path segment: /superpowers/{name}."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this superpower does."""

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def tags(self) -> list[str]:
        return []

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def memory_path(self) -> str:
        return f"/superpowers/{self.name}"

    def bind_memory(self, memory: MemoryManager) -> None:
        self._memory = memory

    def remember(self, key: str, content: str, **kwargs) -> None:
        """Write to this superpower's memory branch."""
        if self._memory:
            self._memory.put(f"{self.memory_path}/{key}", content, **kwargs)

    def recall(self, key: str) -> str | None:
        """Read from this superpower's memory branch."""
        if self._memory:
            node = self._memory.get(f"{self.memory_path}/{key}")
            return node.content if node else None
        return None

    async def activate(self) -> None:
        """Called when the superpower is registered. Override for setup."""
        self._active = True

    async def deactivate(self) -> None:
        """Called when the superpower is removed. Override for cleanup."""
        self._active = False

    @abstractmethod
    def get_tools(self) -> list[BaseTool]:
        """Return LangChain tools that this superpower provides to the agent."""

    def get_status(self) -> dict[str, Any]:
        """Return status info for the dashboard."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "active": self._active,
            "tags": self.tags,
        }
