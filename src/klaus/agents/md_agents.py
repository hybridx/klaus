"""Markdown-based agent definitions — parse .md files into specialist agent configs.

Format:
    # Agent: agent_name
    Description of what the agent specializes in.

    ## Capabilities
    - coding
    - analysis

    ## System Prompt
    You are a specialist in ...

    ## Preferred Model
    granite-code:8b

    ## Preferred Backend
    ollama

    ## Tools
    - search_memory
    - recall
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_AGENT_NAME_RE = re.compile(r"^#\s+Agent:\s*(.+)", re.IGNORECASE)


@dataclass
class AgentSpec:
    """A specialist agent definition loaded from a Markdown file."""

    name: str
    description: str
    system_prompt: str = ""
    capabilities: list[str] = field(default_factory=list)
    preferred_model: str | None = None
    preferred_backend: str | None = None
    tools: list[str] = field(default_factory=list)
    source_file: str = ""


def parse_md_agent(path: Path) -> AgentSpec | None:
    """Parse a single Markdown file into an AgentSpec."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to read MD agent %s: %s", path, exc)
        return None

    lines = text.strip().split("\n")
    if not lines:
        return None

    name_match = _AGENT_NAME_RE.match(lines[0])
    if not name_match:
        logger.warning("MD agent %s: missing '# Agent: name' heading", path.name)
        return None
    agent_name = name_match.group(1).strip().replace(" ", "_").lower()

    desc_lines: list[str] = []
    i = 1
    while i < len(lines) and not lines[i].startswith("##"):
        desc_lines.append(lines[i])
        i += 1
    description = "\n".join(desc_lines).strip() or f"Agent from {path.name}"

    capabilities: list[str] = []
    system_prompt = ""
    preferred_model: str | None = None
    preferred_backend: str | None = None
    tools: list[str] = []

    while i < len(lines):
        heading = lines[i].lower().strip()

        if heading.startswith("## capabilities"):
            i += 1
            while i < len(lines) and not lines[i].startswith("##"):
                line = lines[i].strip()
                if line.startswith("- "):
                    capabilities.append(line[2:].strip())
                i += 1

        elif heading.startswith("## system prompt"):
            i += 1
            prompt_lines: list[str] = []
            while i < len(lines) and not lines[i].startswith("##"):
                prompt_lines.append(lines[i])
                i += 1
            system_prompt = "\n".join(prompt_lines).strip()

        elif heading.startswith("## preferred model"):
            i += 1
            while i < len(lines) and not lines[i].startswith("##"):
                line = lines[i].strip()
                if line:
                    preferred_model = line
                    break
                i += 1
            i += 1

        elif heading.startswith("## preferred backend"):
            i += 1
            while i < len(lines) and not lines[i].startswith("##"):
                line = lines[i].strip()
                if line:
                    preferred_backend = line
                    break
                i += 1
            i += 1

        elif heading.startswith("## tools"):
            i += 1
            while i < len(lines) and not lines[i].startswith("##"):
                line = lines[i].strip()
                if line.startswith("- "):
                    tools.append(line[2:].strip())
                i += 1

        else:
            i += 1

    return AgentSpec(
        name=agent_name,
        description=description,
        system_prompt=system_prompt,
        capabilities=capabilities,
        preferred_model=preferred_model,
        preferred_backend=preferred_backend,
        tools=tools,
        source_file=str(path),
    )


def load_md_agents(directory: str | Path) -> list[AgentSpec]:
    """Load all .md agent definitions from a directory."""
    d = Path(directory)
    if not d.exists():
        logger.info("MD agents directory %s does not exist, skipping", d)
        return []

    agents: list[AgentSpec] = []
    for path in sorted(d.glob("*.md")):
        agent = parse_md_agent(path)
        if agent:
            agents.append(agent)
            logger.info(
                "Loaded MD agent: %s (%s) from %s",
                agent.name, ", ".join(agent.capabilities) or "general", path.name,
            )

    return agents
