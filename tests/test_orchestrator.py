"""Tests for the multi-agent orchestrator."""

from __future__ import annotations

import pytest

from klaus.agents.md_agents import AgentSpec
from klaus.agents.orchestrator import Orchestrator, PlanStep, _chunk_text


class TestPlanStep:
    def test_defaults(self):
        step = PlanStep(index=0, description="Write a poem")
        assert step.status == "pending"
        assert step.task_type is None
        assert step.agent is None
        assert step.depends_on == []
        assert step.result is None

    def test_with_type(self):
        step = PlanStep(index=1, description="Debug code", task_type="coding")
        assert step.task_type == "coding"

    def test_with_dependencies(self):
        step = PlanStep(index=2, description="Summarize", depends_on=[0, 1])
        assert step.depends_on == [0, 1]

    def test_with_agent(self):
        step = PlanStep(index=0, description="Review code", agent="code_expert")
        assert step.agent == "code_expert"


class TestChunkText:
    def test_basic_chunking(self):
        text = "Hello, World!"
        chunks = _chunk_text(text, 5)
        assert chunks == ["Hello", ", Wor", "ld!"]

    def test_exact_size(self):
        text = "12345"
        chunks = _chunk_text(text, 5)
        assert chunks == ["12345"]

    def test_empty_text(self):
        chunks = _chunk_text("", 10)
        assert chunks == []

    def test_single_char_chunks(self):
        chunks = _chunk_text("abc", 1)
        assert chunks == ["a", "b", "c"]


class TestOrchestratorInit:
    def test_requires_model_registry(self):
        class FakeRegistry:
            def get_chat_model(self, **kwargs):
                return None
        class FakeRouter:
            def resolve(self, **kwargs):
                return None

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        assert orch._planner_backend is None
        assert orch._planner_model is None

    def test_custom_planner_config(self):
        class FakeRegistry:
            pass
        class FakeRouter:
            pass

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
            planner_backend="ollama",
            planner_model="qwen3:14b",
        )
        assert orch._planner_backend == "ollama"
        assert orch._planner_model == "qwen3:14b"


class TestResolveStep:
    def test_resolve_sets_backend_and_model(self):
        class FakeDecision:
            backend = "ollama"
            model = "llama3.2"
            reason = "local-first"

        class FakeRouter:
            def resolve(self, **kwargs):
                return FakeDecision()

        class FakeRegistry:
            def model_supports(self, backend, model, capability):
                return True
            async def find_capable_model(self, backend, capability):
                return None

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        step = PlanStep(index=0, description="test", task_type="coding")
        result = orch.resolve_step(step)
        assert result.backend == "ollama"
        assert result.model == "llama3.2"

    def test_resolve_uses_agent_preferences(self):
        class FakeDecision:
            backend = "ollama"
            model = "llama3.2"
            reason = "local-first"

        class FakeRouter:
            def resolve(self, **kwargs):
                return FakeDecision()

        class FakeRegistry:
            def model_supports(self, backend, model, capability):
                return True
            async def find_capable_model(self, backend, capability):
                return None

        agent = AgentSpec(
            name="code_expert",
            description="Coding specialist",
            preferred_backend="ollama",
            preferred_model="granite-code:8b",
        )
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
            agents=[agent],
        )
        step = PlanStep(index=0, description="test", task_type="coding", agent="code_expert")
        result = orch.resolve_step(step)
        assert result.backend == "ollama"
        assert result.model == "granite-code:8b"


class TestApproval:
    def test_set_approval(self):
        class FakeRegistry:
            pass
        class FakeRouter:
            pass

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        orch.set_approval("approve")
        assert orch._approval_result == {"action": "approve", "edits": [], "reason": ""}

    def test_apply_edits(self):
        class FakeRegistry:
            pass
        class FakeRouter:
            pass

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        steps = [
            PlanStep(index=0, description="Write code"),
            PlanStep(index=1, description="Write poem"),
            PlanStep(index=2, description="Summarize"),
        ]
        edits = [
            {"index": 0, "description": "Write Python code"},
            {"index": 2, "remove": True},
        ]
        result = orch._apply_edits(steps, edits)
        assert len(result) == 2
        assert result[0].description == "Write Python code"
        assert result[0].index == 0
        assert result[1].description == "Write poem"
        assert result[1].index == 1
