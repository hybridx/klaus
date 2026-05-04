"""Superpower registry — manages the lifecycle of all capabilities.

The registry is the central place where superpowers are registered,
activated, and discovered. It writes each superpower's metadata into
the memory tree so the agent knows what it can do.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool

from klaus.memory.store import MemoryManager
from klaus.superpowers.base import Superpower

logger = logging.getLogger(__name__)


class SuperpowerRegistry:
    """Manages superpower lifecycle and exposes their tools to the agent."""

    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory
        self._powers: dict[str, Superpower] = {}

    async def register(self, power: Superpower) -> None:
        """Register and activate a superpower."""
        if power.name in self._powers:
            raise ValueError(f"Superpower '{power.name}' is already registered")

        power.bind_memory(self._memory)
        await power.activate()
        self._powers[power.name] = power

        # Write to the memory tree
        self._memory.put(
            power.memory_path,
            content=power.description,
            metadata={
                "version": power.version,
                "active": True,
                "tool_count": len(power.get_tools()),
            },
            tags=power.tags,
        )

        tool_names = [t.name for t in power.get_tools()]
        if tool_names:
            self._memory.put(
                f"{power.memory_path}/tools",
                content=", ".join(tool_names),
                tags=["tools"],
            )

        logger.info(
            "Superpower registered: %s (%d tools)",
            power.name,
            len(tool_names),
        )

    async def unregister(self, name: str) -> None:
        """Deactivate and remove a superpower."""
        power = self._powers.pop(name, None)
        if power is None:
            return

        await power.deactivate()
        self._memory.put(
            power.memory_path,
            content=f"{power.description} [deactivated]",
            metadata={"active": False},
        )
        logger.info("Superpower unregistered: %s", name)

    def get(self, name: str) -> Superpower | None:
        return self._powers.get(name)

    def list_active(self) -> list[dict[str, Any]]:
        return [p.get_status() for p in self._powers.values() if p.is_active]

    def list_all(self) -> list[dict[str, Any]]:
        return [p.get_status() for p in self._powers.values()]

    def collect_tools(self) -> list[BaseTool]:
        """Gather all tools from all active superpowers for the agent."""
        tools: list[BaseTool] = []
        for power in self._powers.values():
            if power.is_active:
                tools.extend(power.get_tools())
        return tools

    async def shutdown_all(self) -> None:
        for name in list(self._powers):
            await self.unregister(name)

    @property
    def active_count(self) -> int:
        return sum(1 for p in self._powers.values() if p.is_active)
