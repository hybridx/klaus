"""Tests for the Markdown-based agent parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from klaus.agents.md_agents import AgentSpec, load_md_agents, parse_md_agent


class TestParseMdAgent:
    def test_valid_agent(self, tmp_path: Path):
        md = tmp_path / "coder.md"
        md.write_text(
            "# Agent: Code Expert\n"
            "Writes and reviews code.\n\n"
            "## Capabilities\n"
            "- coding\n"
            "- debugging\n\n"
            "## System Prompt\n"
            "You are a coding expert.\n\n"
            "## Preferred Model\n"
            "granite-code:8b\n\n"
            "## Preferred Backend\n"
            "ollama\n\n"
            "## Tools\n"
            "- search_memory\n"
            "- recall\n"
        )
        agent = parse_md_agent(md)
        assert agent is not None
        assert agent.name == "code_expert"
        assert agent.description == "Writes and reviews code."
        assert agent.capabilities == ["coding", "debugging"]
        assert agent.system_prompt == "You are a coding expert."
        assert agent.preferred_model == "granite-code:8b"
        assert agent.preferred_backend == "ollama"
        assert agent.tools == ["search_memory", "recall"]

    def test_missing_heading(self, tmp_path: Path):
        md = tmp_path / "bad.md"
        md.write_text("No heading here.\n")
        assert parse_md_agent(md) is None

    def test_minimal_agent(self, tmp_path: Path):
        md = tmp_path / "minimal.md"
        md.write_text("# Agent: simple\nJust a simple agent.\n")
        agent = parse_md_agent(md)
        assert agent is not None
        assert agent.name == "simple"
        assert agent.description == "Just a simple agent."
        assert agent.capabilities == []
        assert agent.preferred_model is None
        assert agent.tools == []

    def test_name_normalization(self, tmp_path: Path):
        md = tmp_path / "spacey.md"
        md.write_text("# Agent: My Cool Agent\nDescription.\n")
        agent = parse_md_agent(md)
        assert agent is not None
        assert agent.name == "my_cool_agent"

    def test_nonexistent_file(self):
        assert parse_md_agent(Path("/nonexistent/agent.md")) is None


class TestLoadMdAgents:
    def test_empty_directory(self, tmp_path: Path):
        assert load_md_agents(tmp_path) == []

    def test_nonexistent_directory(self):
        assert load_md_agents("/nonexistent/agents/") == []

    def test_loads_multiple_agents(self, tmp_path: Path):
        (tmp_path / "a.md").write_text("# Agent: alpha\nFirst agent.\n")
        (tmp_path / "b.md").write_text("# Agent: beta\nSecond agent.\n")
        agents = load_md_agents(tmp_path)
        assert len(agents) == 2
        names = {a.name for a in agents}
        assert names == {"alpha", "beta"}

    def test_skips_invalid_files(self, tmp_path: Path):
        (tmp_path / "good.md").write_text("# Agent: good\nValid agent.\n")
        (tmp_path / "bad.md").write_text("No heading.\n")
        agents = load_md_agents(tmp_path)
        assert len(agents) == 1
        assert agents[0].name == "good"
