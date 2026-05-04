"""Memory Tools superpower — lets the agent read/write its own memory tree.

This gives the agent self-awareness about its memory and the ability to
store facts, recall information, and organize knowledge on its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool

from klaus.superpowers.base import Superpower

if TYPE_CHECKING:
    from klaus.db import Database
    from klaus.memory.store import MemoryManager


class MemoryTools(Superpower):
    """Gives the agent direct access to the memory tree."""

    def __init__(self, memory_manager: MemoryManager, db: Database | None = None) -> None:
        super().__init__()
        self._mm = memory_manager
        self._db = db

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "Read, write, and search the persistent memory tree"

    @property
    def tags(self) -> list[str]:
        return ["memory", "knowledge", "core"]

    def get_tools(self) -> list[StructuredTool]:
        mm = self._mm
        db = self._db

        async def remember(path: str, content: str) -> str:
            """Store information in the memory tree at the given path."""
            mm.put(f"/knowledge/{path.strip('/')}", content)
            await mm.flush_embeddings()
            return f"Stored at /knowledge/{path.strip('/')}"

        async def recall(path: str) -> str:
            """Retrieve information from the memory tree."""
            node = mm.get(f"/knowledge/{path.strip('/')}")
            if node is None:
                return f"Nothing found at /knowledge/{path}"
            return node.content or "(empty node)"

        async def search_memory(query: str) -> str:
            """Search memory using semantic + keyword hybrid search."""
            from klaus.memory.index import MemoryIndex

            index = MemoryIndex(mm.tree, db=db)
            results = await index.hybrid_search(query, root_path="/", max_results=8)
            if not results:
                return "No matching memories found."
            lines = []
            for r in results:
                snippet = r.node.content[:200] if r.node.content else "(empty)"
                lines.append(f"[{r.path}] ({r.match_reason}, score={r.score:.2f}) {snippet}")
            return "\n".join(lines)

        async def list_memory(path: str = "/") -> str:
            """List children at a memory tree path."""
            children = mm.ls(path)
            if not children:
                return f"No children at {path}"
            return ", ".join(children)

        return [
            StructuredTool.from_function(
                coroutine=remember,
                name="remember",
                description="Store a fact or piece of information in persistent memory",
            ),
            StructuredTool.from_function(
                coroutine=recall,
                name="recall",
                description="Retrieve a specific piece of information from memory by path",
            ),
            StructuredTool.from_function(
                coroutine=search_memory,
                name="search_memory",
                description="Search memory for information related to a query",
            ),
            StructuredTool.from_function(
                coroutine=list_memory,
                name="list_memory",
                description="List contents of a memory tree path",
            ),
        ]
