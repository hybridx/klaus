"""Skills superpower — Hermes-inspired self-improving skill system.

The agent creates reusable procedures from experience, retrieves them
for similar tasks, and improves them over time. Skills are stored in
the memory tree under /knowledge/skills/.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool

from klaus.superpowers.base import Superpower

if TYPE_CHECKING:
    from klaus.memory.store import MemoryManager

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path("data/skills")


class SkillsSuperpower(Superpower):
    """Self-improving skill system inspired by Hermes Agent."""

    def __init__(self, memory_manager: MemoryManager, skills_dir: Path | None = None) -> None:
        super().__init__()
        self._mm = memory_manager
        self._skills_dir = skills_dir or _SKILLS_DIR

    @property
    def name(self) -> str:
        return "skills"

    @property
    def description(self) -> str:
        return "Create, retrieve, and improve reusable skills from experience"

    @property
    def tags(self) -> list[str]:
        return ["skills", "learning", "self-improvement", "core"]

    async def activate(self) -> None:
        await super().activate()
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        loaded = 0
        for md_file in self._skills_dir.glob("*.md"):
            name = md_file.stem.replace(" ", "-").lower()
            path = f"/knowledge/skills/{name}"
            if self._mm.get(path) is not None:
                continue
            content = md_file.read_text(encoding="utf-8").strip()
            if not content:
                continue
            self._mm.put(
                path,
                content=content,
                metadata={
                    "usage_count": 0,
                    "created_at": time.time(),
                    "created_by": "file",
                    "source_file": str(md_file),
                    "version": 1,
                },
                tags=["skill", "imported"],
            )
            loaded += 1
        if loaded:
            logger.info("Loaded %d skill(s) from %s", loaded, self._skills_dir)
            await self._mm.flush_embeddings()

    def get_tools(self) -> list[StructuredTool]:
        mm = self._mm
        skills_dir = self._skills_dir

        async def create_skill(name: str, description: str, procedure: str, tags: str = "") -> str:
            """Create a new reusable skill from experience.

            Args:
                name: Short identifier (e.g. 'web-research', 'code-review')
                description: What this skill does
                procedure: Step-by-step instructions in markdown
                tags: Comma-separated tags for searching
            """
            path = f"/knowledge/skills/{name.strip().replace(' ', '-').lower()}"

            existing = mm.get(path)
            if existing and existing.content:
                return f"Skill '{name}' already exists. Use improve_skill to update it."

            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
            tag_list.append("skill")

            mm.put(
                path,
                content=f"## {name}\n\n{description}\n\n### Procedure\n\n{procedure}",
                metadata={
                    "usage_count": 0,
                    "created_at": time.time(),
                    "last_used": None,
                    "created_by": "agent",
                    "version": 1,
                },
                tags=tag_list,
            )

            await mm.flush_embeddings()
            return f"Skill '{name}' created at {path}. It will be available for future tasks."

        async def use_skill(name: str) -> str:
            """Retrieve a skill's procedure to follow for the current task."""
            path = f"/knowledge/skills/{name.strip().replace(' ', '-').lower()}"
            node = mm.get(path)
            if node is None:
                results = mm.search(name, root_path="/knowledge/skills", max_results=3)
                if results:
                    suggestions = [f"- {p.split('/')[-1]}" for p, _, _ in results]
                    return f"Skill '{name}' not found. Similar skills:\n" + "\n".join(suggestions)
                return f"Skill '{name}' not found and no similar skills exist."

            meta = node.metadata or {}
            meta["usage_count"] = meta.get("usage_count", 0) + 1
            meta["last_used"] = time.time()
            mm.put(path, content=node.content, metadata=meta, tags=node.tags)

            return node.content

        async def improve_skill(name: str, improvement: str) -> str:
            """Improve an existing skill with better steps or corrections.

            Args:
                name: The skill to improve
                improvement: What to change or add (will be appended as a new version note)
            """
            path = f"/knowledge/skills/{name.strip().replace(' ', '-').lower()}"
            node = mm.get(path)
            if node is None:
                return f"Skill '{name}' not found. Create it first with create_skill."

            meta = node.metadata or {}
            version = meta.get("version", 1) + 1
            meta["version"] = version
            meta["improved_at"] = time.time()

            updated = node.content + f"\n\n### Improvement (v{version})\n\n{improvement}"
            mm.put(path, content=updated, metadata=meta, tags=node.tags)

            return f"Skill '{name}' improved to v{version}."

        async def list_skills(query: str = "") -> str:
            """List available skills, optionally filtered by a search query."""
            if query:
                results = mm.search(query, root_path="/knowledge/skills", max_results=10)
                if not results:
                    return "No matching skills found."
                lines = []
                for path, node, _score in results:
                    name = path.split("/")[-1]
                    meta = node.metadata or {}
                    usage = meta.get("usage_count", 0)
                    lines.append(f"- **{name}** (used {usage}x): {node.content[:80]}...")
                return "\n".join(lines)

            children = mm.ls("/knowledge/skills")
            if not children:
                return "No skills created yet. Use create_skill after completing complex tasks."

            lines = []
            for child_name in children:
                node = mm.get(f"/knowledge/skills/{child_name}")
                if node:
                    meta = node.metadata or {}
                    usage = meta.get("usage_count", 0)
                    version = meta.get("version", 1)
                    lines.append(f"- **{child_name}** v{version} (used {usage}x)")
            return "\n".join(lines) if lines else "No skills found."

        async def import_skill(file_path: str) -> str:
            """Import a skill from a markdown (.md) file on disk.

            Args:
                file_path: Path to the .md file (absolute or relative to data/skills/)
            """
            p = Path(file_path)
            if not p.is_absolute():
                p = skills_dir / p
            if not p.exists():
                return f"File not found: {p}"
            if p.suffix.lower() != ".md":
                return f"Only .md files are supported, got: {p.suffix}"

            content = p.read_text(encoding="utf-8").strip()
            if not content:
                return f"File is empty: {p}"

            skill_name = p.stem.replace(" ", "-").lower()
            skill_path = f"/knowledge/skills/{skill_name}"

            existing = mm.get(skill_path)
            if existing and existing.content:
                return f"Skill '{skill_name}' already exists. Use improve_skill to update."

            mm.put(
                skill_path,
                content=content,
                metadata={
                    "usage_count": 0,
                    "created_at": time.time(),
                    "created_by": "file",
                    "source_file": str(p),
                    "version": 1,
                },
                tags=["skill", "imported"],
            )
            await mm.flush_embeddings()
            return f"Skill '{skill_name}' imported from {p.name}"

        return [
            StructuredTool.from_function(
                coroutine=create_skill,
                name="create_skill",
                description="Create a reusable skill/procedure from experience for future tasks",
            ),
            StructuredTool.from_function(
                coroutine=use_skill,
                name="use_skill",
                description="Retrieve a skill's procedure to follow for the current task",
            ),
            StructuredTool.from_function(
                coroutine=improve_skill,
                name="improve_skill",
                description="Improve an existing skill with better steps or corrections",
            ),
            StructuredTool.from_function(
                coroutine=list_skills,
                name="list_skills",
                description="List all available skills or search for relevant ones",
            ),
            StructuredTool.from_function(
                coroutine=import_skill,
                name="import_skill",
                description="Import a skill from a markdown (.md) file",
            ),
        ]
