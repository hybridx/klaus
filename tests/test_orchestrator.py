"""Tests for the multi-agent orchestrator.

Covers: plan steps, text chunking, init, resolve routing (sync + async),
memory corrections, approval lifecycle, planner prompt generation,
image-aware routing, end-to-end pipeline simulation, and complexity detection.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from klaus.agents.md_agents import AgentSpec
from klaus.agents.orchestrator import (
    Orchestrator,
    PlanStep,
    StepResult,
    _build_planner_prompt,
    _chunk_text,
)
from klaus.config.settings import TaskRoutingRule
from klaus.memory.store import MemoryManager
from klaus.models.base import ChatMessage


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


class TestLoadCorrections:
    @pytest.mark.asyncio
    async def test_no_memory_returns_empty(self):
        class FakeRegistry:
            pass
        class FakeRouter:
            pass

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        result = await orch._load_corrections("test query")
        assert result == ""

    @pytest.mark.asyncio
    async def test_with_matching_corrections(self):
        class FakeRegistry:
            pass
        class FakeRouter:
            pass

        mm = MemoryManager()
        mm.tree.put(
            "/knowledge/plan-corrections/c1",
            "Use granite-code for coding tasks",
            tags=["plan-correction"],
        )
        mm.tree.put(
            "/knowledge/plan-corrections/c2",
            "Always run tests after code generation",
            tags=["plan-correction"],
        )

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
            memory=mm,
        )
        result = await orch._load_corrections("plan correction coding")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_no_matching_corrections(self):
        class FakeRegistry:
            pass
        class FakeRouter:
            pass

        mm = MemoryManager()
        mm.tree.put("/knowledge/unrelated", "some unrelated data", tags=["other"])

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
            memory=mm,
        )
        result = await orch._load_corrections("zzz nothing matches zzz")
        assert result == ""


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


class TestPlannerPromptImages:
    def test_prompt_without_images(self):
        prompt = _build_planner_prompt([], has_images=False)
        assert '"image"' in prompt  # task_type list includes "image"
        assert "The user attached images" not in prompt

    def test_prompt_with_images(self):
        prompt = _build_planner_prompt([], has_images=True)
        assert "attached" in prompt.lower()
        assert '"image"' in prompt
        assert "MUST" in prompt

    def test_prompt_includes_image_task_type(self):
        prompt = _build_planner_prompt([])
        assert '"image"' in prompt


class TestResolveStepAsync:
    @pytest.mark.asyncio
    async def test_image_step_gets_vision_model(self):
        class FakeDecision:
            backend = "ollama"
            model = "llama3.2"
            reason = "task routing"

        class FakeRouter:
            def resolve(self, **kwargs):
                return FakeDecision()

        class FakeRegistry:
            def model_supports(self, backend, model, capability):
                if capability == "vision":
                    return model == "gemma4:latest"
                return True

            async def find_capable_model(self, backend, capability):
                if capability == "vision":
                    return "gemma4:latest"
                return None

            def list_backends(self):
                return ["ollama"]

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        step = PlanStep(index=0, description="Describe the image", task_type="image")
        result = await orch.resolve_step_async(step)
        assert result.model == "gemma4:latest"
        assert result.backend == "ollama"

    @pytest.mark.asyncio
    async def test_coding_step_keeps_own_model(self):
        class FakeDecision:
            backend = "ollama"
            model = "granite-code:8b"
            reason = "task routing"

        class FakeRouter:
            def resolve(self, **kwargs):
                return FakeDecision()

        class FakeRegistry:
            def model_supports(self, backend, model, capability):
                return True

            async def find_capable_model(self, backend, capability):
                return None

            def list_backends(self):
                return ["ollama"]

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        step = PlanStep(index=1, description="Write hello world", task_type="coding")
        result = await orch.resolve_step_async(step)
        assert result.model == "granite-code:8b"

    @pytest.mark.asyncio
    async def test_image_step_cross_backend_fallback(self):
        """If the primary backend has no vision model, find one on another backend."""
        class FakeDecision:
            backend = "openai"
            model = "gpt-4"
            reason = "auto"

        class FakeRouter:
            def resolve(self, **kwargs):
                return FakeDecision()

        class FakeRegistry:
            def model_supports(self, backend, model, capability):
                return False

            async def find_capable_model(self, backend, capability):
                if capability == "vision" and backend == "ollama":
                    return "gemma4:latest"
                return None

            def list_backends(self):
                return ["openai", "ollama"]

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        step = PlanStep(index=0, description="Analyze image", task_type="image")
        result = await orch.resolve_step_async(step)
        assert result.model == "gemma4:latest"
        assert result.backend == "ollama"

    @pytest.mark.asyncio
    async def test_mixed_request_routes_differently(self):
        """Image step → vision model, coding step → code model, creative → default."""
        call_log = []

        class FakeDecision:
            def __init__(self, task):
                self.backend = "ollama"
                self.model = {
                    "image": "llama3.2",
                    "coding": "granite-code:8b",
                    "creative": "dolphin-llama3",
                }.get(task, "llama3.2")
                self.reason = "task routing"

        class FakeRouter:
            def resolve(self, **kwargs):
                task = kwargs.get("task", "general")
                call_log.append(task)
                return FakeDecision(task)

        class FakeRegistry:
            def model_supports(self, backend, model, capability):
                if capability == "vision":
                    return model == "gemma4:latest"
                return True

            async def find_capable_model(self, backend, capability):
                if capability == "vision":
                    return "gemma4:latest"
                return None

            def list_backends(self):
                return ["ollama"]

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )

        steps = [
            PlanStep(index=0, description="Describe the image", task_type="image"),
            PlanStep(index=1, description="Write hello world", task_type="coding"),
            PlanStep(index=2, description="Write a poem", task_type="creative"),
        ]

        for step in steps:
            await orch.resolve_step_async(step)

        assert steps[0].model == "gemma4:latest"
        assert steps[1].model == "granite-code:8b"
        assert steps[2].model == "dolphin-llama3"


# ── Helpers for the end-to-end harness ────────────────────────────────────────


_ROUTING_RULES = {
    "coding": TaskRoutingRule(
        preferred_backend="ollama", preferred_model="granite-code:8b",
        description="Programming tasks", keywords=["code", "function", "program"],
    ),
    "creative": TaskRoutingRule(
        preferred_backend="ollama", preferred_model="dolphin-llama3",
        description="Creative writing", keywords=["poem", "story", "creative"],
    ),
    "image": TaskRoutingRule(
        preferred_backend="ollama", preferred_model="gemma4:latest",
        description="Image analysis", keywords=["image", "photo", "describe"],
    ),
    "chat": TaskRoutingRule(
        preferred_backend="ollama", preferred_model="llama3.2",
        description="General Q&A", keywords=["hello", "help", "explain"],
    ),
}

MODEL_MAP = {
    "image": "gemma4:latest",
    "coding": "granite-code:8b",
    "creative": "dolphin-llama3",
    "chat": "llama3.2",
}


@dataclass
class _FakeDecision:
    backend: str = "ollama"
    model: str | None = None
    reason: str = "task routing"


class FakeRouter:
    """Routes tasks to different models based on _ROUTING_RULES."""

    def __init__(self):
        self._rules = dict(_ROUTING_RULES)

    def resolve(self, task=None, **kwargs):
        rule = self._rules.get(task)
        if rule:
            return _FakeDecision(
                backend=rule.preferred_backend or "ollama",
                model=rule.preferred_model,
            )
        return _FakeDecision(model="llama3.2")

    def get_rules(self):
        return dict(self._rules)

    def set_rule(self, task, rule):
        self._rules[task] = rule

    def remove_rule(self, task):
        self._rules.pop(task, None)


class FakeRegistry:
    """Model registry that knows which models support which capabilities."""

    def model_supports(self, backend, model, capability):
        if capability == "vision":
            return model == "gemma4:latest"
        if capability == "tools":
            return model != "gemma4:latest"
        return True

    async def find_capable_model(self, backend, capability):
        if capability == "vision":
            return "gemma4:latest"
        return "llama3.2"

    def list_backends(self):
        return ["ollama"]

    def get_chat_model(self, backend=None, model=None, temperature=None):
        if temperature and temperature <= 0.3:
            return _FakePlannerLLM()
        return _FakeExecutorLLM(model=model)


EXPECTED_PLAN_JSON = [
    {"description": "Analyze the attached image", "task_type": "image", "depends_on": []},
    {"description": "Write a hello world program with the name Deepesh", "task_type": "coding", "depends_on": []},
    {"description": "Write a poem about the hello world program", "task_type": "creative", "depends_on": [1]},
]


class _FakePlannerLLM:
    """Returns the pre-defined 3-step JSON plan when invoked."""

    async def ainvoke(self, messages, **kwargs):
        return MagicMock(content=json.dumps(EXPECTED_PLAN_JSON))


class _FakeExecutorLLM:
    """Returns model-attributed text for each step."""

    def __init__(self, model=None):
        self.model = model

    async def ainvoke(self, messages, **kwargs):
        return MagicMock(content=f"[{self.model}] executed")


# ── Complexity detection ──────────────────────────────────────────────────────


class TestIsComplex:
    """Test _is_complex from the events module."""

    @staticmethod
    def _is_complex(text):
        import re
        from klaus.api.routes.events import _is_complex
        return _is_complex(text)

    def test_simple_greeting(self):
        assert not self._is_complex("Hello, how are you?")

    def test_simple_question(self):
        assert not self._is_complex("What is machine learning?")

    def test_multiple_sentences(self):
        assert self._is_complex("Write me a function. Then create a test for it.")

    def test_and_also_marker(self):
        assert self._is_complex("Fix the bug and also write documentation")

    def test_then_marker(self):
        assert self._is_complex("First analyze this then summarize the results")

    def test_three_action_verbs(self):
        assert self._is_complex(
            "create a hello world program and write a poem and tell me what the image is about"
        )

    def test_two_verbs_not_complex(self):
        assert not self._is_complex("write a function and explain how it works")

    def test_numbered_list(self):
        assert self._is_complex(
            "I need you to: 1. Create a function. 2. Write tests. 3. Document it."
        )


# ── Planner prompt quality ───────────────────────────────────────────────────


class TestPlannerPromptRouting:
    """Planner prompt should include the actual routing rules so the LLM knows
    which task types map to which specialist models."""

    def test_prompt_lists_available_models(self):
        rules = {
            "coding": {"preferred_model": "granite-code:8b", "description": "Programming tasks"},
            "creative": {"preferred_model": "dolphin-llama3", "description": "Creative writing"},
            "image": {"preferred_model": "gemma4:latest", "description": "Image analysis"},
        }
        prompt = _build_planner_prompt([], routing_rules=rules)
        assert "granite-code:8b" in prompt
        assert "dolphin-llama3" in prompt
        assert "gemma4:latest" in prompt
        assert "Programming tasks" in prompt

    def test_prompt_without_rules_uses_defaults(self):
        prompt = _build_planner_prompt([])
        assert '"coding"' in prompt
        assert '"creative"' in prompt
        assert '"image"' in prompt

    def test_prompt_instructs_separate_steps(self):
        prompt = _build_planner_prompt([])
        assert "SEPARATE" in prompt or "separate" in prompt
        assert "DIFFERENT" in prompt or "different" in prompt

    def test_prompt_with_images_and_rules(self):
        rules = {
            "image": {"preferred_model": "gemma4:latest", "description": "Vision"},
            "coding": {"preferred_model": "granite-code:8b", "description": "Code"},
        }
        prompt = _build_planner_prompt([], has_images=True, routing_rules=rules)
        assert "attached" in prompt.lower()
        assert "gemma4:latest" in prompt
        assert "granite-code:8b" in prompt


# ── Approval lifecycle ───────────────────────────────────────────────────────


class TestPlannerFallback:
    """When the LLM planner returns 1 step or invalid JSON, the deterministic
    splitter should kick in and produce multiple steps."""

    @pytest.mark.asyncio
    async def test_single_step_triggers_fallback(self):
        """Planner returns 1 step → fallback splits into multiple."""

        class SingleStepLLM:
            async def ainvoke(self, messages, **kwargs):
                return MagicMock(content=json.dumps([
                    {"description": DUMMY_PROMPT, "task_type": "creative", "depends_on": []}
                ]))

        class SingleStepRegistry(FakeRegistry):
            def get_chat_model(self, backend=None, model=None, temperature=None):
                return SingleStepLLM()

        orch = Orchestrator(
            model_registry=SingleStepRegistry(),
            task_router=FakeRouter(),
        )
        steps = await orch.plan(DUMMY_PROMPT, has_images=True)
        assert len(steps) >= 2, f"Fallback should produce >=2 steps, got {len(steps)}"
        task_types = {s.task_type for s in steps}
        assert "image" in task_types, "Fallback should add an image step when has_images=True"

    @pytest.mark.asyncio
    async def test_invalid_json_triggers_fallback(self):
        """Planner returns garbage → fallback uses splitter."""

        class BadJsonLLM:
            async def ainvoke(self, messages, **kwargs):
                return MagicMock(content="Sure! I'll help with all that.")

        class BadJsonRegistry(FakeRegistry):
            def get_chat_model(self, backend=None, model=None, temperature=None):
                return BadJsonLLM()

        orch = Orchestrator(
            model_registry=BadJsonRegistry(),
            task_router=FakeRouter(),
        )
        steps = await orch.plan(DUMMY_PROMPT)
        assert len(steps) >= 2, f"Fallback should produce >=2 steps, got {len(steps)}"

    @pytest.mark.asyncio
    async def test_good_plan_not_overridden(self):
        """When LLM returns a proper multi-step plan, don't override it."""
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        steps = await orch.plan(DUMMY_PROMPT, has_images=True)
        assert len(steps) == 3
        task_types = {s.task_type for s in steps}
        assert task_types == {"image", "coding", "creative"}

    def test_fallback_split_with_images(self):
        text = "create a hello world program and write a poem"
        steps = Orchestrator._fallback_split(text, has_images=True)
        task_types = {s.task_type for s in steps}
        assert "image" in task_types, "Should inject an image step when has_images=True"

    def test_fallback_split_without_images(self):
        text = "create a hello world program and write a poem"
        steps = Orchestrator._fallback_split(text, has_images=False)
        task_types = {s.task_type for s in steps}
        assert "image" not in task_types


class TestApprovalLifecycle:
    def test_prepare_then_set(self):
        orch = Orchestrator(model_registry=FakeRegistry(), task_router=FakeRouter())
        orch.prepare_for_approval()
        assert orch._approval_event is not None
        assert not orch._approval_event.is_set()
        orch.set_approval("approve")
        assert orch._approval_event.is_set()

    @pytest.mark.asyncio
    async def test_wait_receives_approval(self):
        orch = Orchestrator(model_registry=FakeRegistry(), task_router=FakeRouter())
        orch.prepare_for_approval()

        async def approve_later():
            await asyncio.sleep(0.05)
            orch.set_approval("approve")

        asyncio.create_task(approve_later())
        result = await orch._wait_for_approval(timeout=2.0)
        assert result["action"] == "approve"

    @pytest.mark.asyncio
    async def test_wait_receives_rejection(self):
        orch = Orchestrator(model_registry=FakeRegistry(), task_router=FakeRouter())
        orch.prepare_for_approval()

        async def reject_later():
            await asyncio.sleep(0.05)
            orch.set_approval("reject", reason="bad plan")

        asyncio.create_task(reject_later())
        result = await orch._wait_for_approval(timeout=2.0)
        assert result["action"] == "reject"
        assert result["reason"] == "bad plan"

    @pytest.mark.asyncio
    async def test_wait_receives_edit(self):
        orch = Orchestrator(model_registry=FakeRegistry(), task_router=FakeRouter())
        orch.prepare_for_approval()

        async def edit_later():
            await asyncio.sleep(0.05)
            orch.set_approval(
                "edit",
                edits=[{"index": 0, "description": "Better description"}],
                reason="needs clarity",
            )

        asyncio.create_task(edit_later())
        result = await orch._wait_for_approval(timeout=2.0)
        assert result["action"] == "edit"
        assert len(result["edits"]) == 1
        assert result["reason"] == "needs clarity"

    @pytest.mark.asyncio
    async def test_timeout_auto_approves(self):
        orch = Orchestrator(model_registry=FakeRegistry(), task_router=FakeRouter())
        orch.prepare_for_approval()
        result = await orch._wait_for_approval(timeout=0.1)
        assert result["action"] == "approve"

    @pytest.mark.asyncio
    async def test_no_race_condition_set_before_wait(self):
        """set_approval before prepare_for_approval should not pre-trigger."""
        orch = Orchestrator(model_registry=FakeRegistry(), task_router=FakeRouter())
        orch.set_approval("reject", reason="stale")
        orch.prepare_for_approval()

        async def approve_later():
            await asyncio.sleep(0.05)
            orch.set_approval("approve")

        asyncio.create_task(approve_later())
        result = await orch._wait_for_approval(timeout=2.0)
        assert result["action"] == "approve"


# ── End-to-end pipeline simulation ──────────────────────────────────────────


DUMMY_PROMPT = (
    "Create a hello world program with my name Deepesh "
    "and write a poem about it "
    "and tell me what the attached image is about"
)


def _make_fake_executor(call_log: list[dict] | None = None):
    """Return a fake execute_step bound method that logs calls and returns
    predictable, model-attributed StepResults.

    Mirrors the real execute_step's image filtering: only image-type steps
    actually receive images.
    """

    async def fake_execute_step(self, step, context="", images=None):
        step_images = images if (step.task_type == "image" and images) else None
        has_images = step_images is not None and len(step_images) > 0
        entry = {
            "index": step.index,
            "task_type": step.task_type,
            "model": step.model,
            "backend": step.backend,
            "has_images": has_images,
            "context_len": len(context),
        }
        if call_log is not None:
            call_log.append(entry)
        text = f"[{step.model}] Result for step {step.index}: {step.description}"
        return StepResult(text=text, reasoning=f"Thinking about {step.task_type}")

    return fake_execute_step


def _patch_executor(orch: Orchestrator, call_log: list[dict] | None = None):
    """Monkey-patch execute_step on an Orchestrator instance."""
    orch.execute_step = _make_fake_executor(call_log).__get__(orch, Orchestrator)


class TestEndToEndPipeline:
    """Full orchestrator pipeline: plan → approve → execute → per-step results.

    Uses FakeLLM so no real model calls are made. Validates that:
    1. The planner creates 3 separate steps with distinct task types
    2. Each step resolves to a different specialist model
    3. Approval actually blocks until approved
    4. Each step produces a result attributed to the correct model
    5. Image steps receive the image, non-image steps don't
    """

    @pytest.mark.asyncio
    async def test_full_pipeline_with_approval(self):
        call_log: list[dict] = []
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        _patch_executor(orch, call_log)

        messages = [
            ChatMessage(role="user", content=DUMMY_PROMPT, images=["base64imagedata"]),
        ]

        events: list[dict] = []

        async def auto_approve():
            """Wait for awaiting_approval then approve."""
            while True:
                await asyncio.sleep(0.02)
                if orch._approval_event and not orch._approval_event.is_set():
                    orch.set_approval("approve")
                    return

        approve_task = asyncio.create_task(auto_approve())

        async for event in orch.run(messages=messages, metadata={"chat_id": "test-1"}):
            events.append(event)

        await approve_task

        event_types = [e["type"] for e in events]

        assert "status" in event_types
        assert "plan.created" in event_types
        assert "plan.awaiting_approval" in event_types
        assert "plan.approved" in event_types
        assert event_types.count("plan.step_start") == 3
        assert event_types.count("plan.step_done") == 3
        assert "done" in event_types

        plan_event = next(e for e in events if e["type"] == "plan.created")
        plan = plan_event["plan"]
        assert len(plan) == 3

        task_types = {s["task_type"] for s in plan}
        assert "image" in task_types
        assert "coding" in task_types
        assert "creative" in task_types

        models_used = {s["model"] for s in plan}
        assert len(models_used) == 3, f"Expected 3 distinct models, got {models_used}"
        assert "gemma4:latest" in models_used
        assert "granite-code:8b" in models_used
        assert "dolphin-llama3" in models_used

        step_done_events = [e for e in events if e["type"] == "plan.step_done"]
        for sde in step_done_events:
            assert sde["result"], f"Step {sde['index']} has no result"
            assert sde["backend"] == "ollama"
            assert sde["model"] in models_used

        assert len(call_log) == 3

    @pytest.mark.asyncio
    async def test_rejection_stops_execution(self):
        call_log: list[dict] = []
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        _patch_executor(orch, call_log)

        messages = [ChatMessage(role="user", content=DUMMY_PROMPT)]

        async def auto_reject():
            while True:
                await asyncio.sleep(0.02)
                if orch._approval_event and not orch._approval_event.is_set():
                    orch.set_approval("reject", reason="I want a different approach")
                    return

        reject_task = asyncio.create_task(auto_reject())

        events = []
        async for event in orch.run(messages=messages, metadata={"chat_id": "test-2"}):
            events.append(event)

        await reject_task

        event_types = [e["type"] for e in events]
        assert "plan.rejected" in event_types
        assert "plan.step_start" not in event_types
        assert "done" in event_types
        assert len(call_log) == 0, "No steps should execute after rejection"

    @pytest.mark.asyncio
    async def test_edit_modifies_plan_before_execution(self):
        call_log: list[dict] = []
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        _patch_executor(orch, call_log)

        messages = [ChatMessage(role="user", content=DUMMY_PROMPT)]

        async def auto_edit():
            while True:
                await asyncio.sleep(0.02)
                if orch._approval_event and not orch._approval_event.is_set():
                    orch.set_approval(
                        "edit",
                        edits=[{"index": 2, "remove": True}],
                        reason="skip the poem",
                    )
                    return

        edit_task = asyncio.create_task(auto_edit())

        events = []
        async for event in orch.run(messages=messages, metadata={"chat_id": "test-3"}):
            events.append(event)

        await edit_task

        event_types = [e["type"] for e in events]
        assert "plan.revised" in event_types
        assert event_types.count("plan.step_start") == 2
        assert event_types.count("plan.step_done") == 2
        assert len(call_log) == 2, "Only 2 steps should run after removing one"

        revised_event = next(e for e in events if e["type"] == "plan.revised")
        revised_plan = revised_event["plan"]
        assert len(revised_plan) == 2
        task_types_left = {s["task_type"] for s in revised_plan}
        assert "creative" not in task_types_left

    @pytest.mark.asyncio
    async def test_image_only_passed_to_image_step(self):
        """Verify execute_step receives images only for image-type steps."""
        call_log: list[dict] = []
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        _patch_executor(orch, call_log)

        messages = [
            ChatMessage(role="user", content=DUMMY_PROMPT, images=["base64img"]),
        ]

        async def auto_approve():
            while True:
                await asyncio.sleep(0.02)
                if orch._approval_event and not orch._approval_event.is_set():
                    orch.set_approval("approve")
                    return

        approve_task = asyncio.create_task(auto_approve())
        async for _ in orch.run(messages=messages, metadata={"chat_id": "test-4"}):
            pass
        await approve_task

        assert len(call_log) == 3
        image_steps = [c for c in call_log if c["task_type"] == "image"]
        non_image_steps = [c for c in call_log if c["task_type"] != "image"]

        for s in image_steps:
            assert s["has_images"], f"Image step {s['index']} didn't receive images"
            assert s["model"] == "gemma4:latest"
        for s in non_image_steps:
            assert not s["has_images"], f"Non-image step {s['index']} received images"

    @pytest.mark.asyncio
    async def test_no_consolidation_step(self):
        """Verify there is no 'consolidating' status or 'plan.consolidated' event."""
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        _patch_executor(orch)

        messages = [ChatMessage(role="user", content=DUMMY_PROMPT)]

        async def auto_approve():
            while True:
                await asyncio.sleep(0.02)
                if orch._approval_event and not orch._approval_event.is_set():
                    orch.set_approval("approve")
                    return

        approve_task = asyncio.create_task(auto_approve())
        events = []
        async for event in orch.run(messages=messages, metadata={"chat_id": "test-5"}):
            events.append(event)
        await approve_task

        event_types = [e["type"] for e in events]
        assert "plan.consolidated" not in event_types
        statuses = [e["detail"] for e in events if e["type"] == "status"]
        assert not any("consolidat" in s.lower() for s in statuses)

    @pytest.mark.asyncio
    async def test_step_results_attributed_to_correct_model(self):
        """Each step_done event must carry the model that executed it."""
        call_log: list[dict] = []
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        _patch_executor(orch, call_log)

        messages = [
            ChatMessage(role="user", content=DUMMY_PROMPT, images=["img"]),
        ]

        async def auto_approve():
            while True:
                await asyncio.sleep(0.02)
                if orch._approval_event and not orch._approval_event.is_set():
                    orch.set_approval("approve")
                    return

        approve_task = asyncio.create_task(auto_approve())
        events = []
        async for event in orch.run(messages=messages, metadata={"chat_id": "test-6"}):
            events.append(event)
        await approve_task

        step_done = [e for e in events if e["type"] == "plan.step_done"]
        assert len(step_done) == 3

        for sde in step_done:
            assert sde["model"] in sde["result"], (
                f"Step {sde['index']} result should mention its model {sde['model']}"
            )
            assert sde["model"] == call_log[sde["index"]]["model"]

    @pytest.mark.asyncio
    async def test_dependent_step_receives_context(self):
        """Step 2 depends on step 1, so it should receive non-empty context."""
        call_log: list[dict] = []
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        _patch_executor(orch, call_log)

        messages = [ChatMessage(role="user", content=DUMMY_PROMPT)]

        async def auto_approve():
            while True:
                await asyncio.sleep(0.02)
                if orch._approval_event and not orch._approval_event.is_set():
                    orch.set_approval("approve")
                    return

        approve_task = asyncio.create_task(auto_approve())
        async for _ in orch.run(messages=messages, metadata={"chat_id": "test-7"}):
            pass
        await approve_task

        # SENSE always injects "Original user request: ..." so independent steps
        # still get a baseline context. Dependent steps get strictly more.
        independent_steps = [c for c in call_log if c["index"] in (0, 1)]
        ind_lens = [s["context_len"] for s in independent_steps]

        creative_step = next(c for c in call_log if c["task_type"] == "creative")
        assert creative_step["context_len"] > max(ind_lens), (
            "Creative step depends on coding step and should receive "
            "dependency results on top of the baseline context"
        )

    @pytest.mark.asyncio
    async def test_skip_approval_when_not_required(self):
        """When require_approval=False, the plan executes immediately."""
        call_log: list[dict] = []
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        _patch_executor(orch, call_log)

        messages = [ChatMessage(role="user", content=DUMMY_PROMPT)]

        events = []
        async for event in orch.run(
            messages=messages,
            metadata={"chat_id": "test-8"},
            require_approval=False,
        ):
            events.append(event)

        event_types = [e["type"] for e in events]
        assert "plan.awaiting_approval" not in event_types
        assert "plan.approved" not in event_types
        assert event_types.count("plan.step_done") == 3
        assert len(call_log) == 3

    @pytest.mark.asyncio
    async def test_event_ordering(self):
        """Events must follow: status → plan.created → awaiting → approved → steps → done."""
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        _patch_executor(orch)

        messages = [ChatMessage(role="user", content=DUMMY_PROMPT)]

        async def auto_approve():
            while True:
                await asyncio.sleep(0.02)
                if orch._approval_event and not orch._approval_event.is_set():
                    orch.set_approval("approve")
                    return

        approve_task = asyncio.create_task(auto_approve())
        events = []
        async for event in orch.run(messages=messages, metadata={"chat_id": "test-9"}):
            events.append(event)
        await approve_task

        types = [e["type"] for e in events]

        status_idx = types.index("status")
        created_idx = types.index("plan.created")
        awaiting_idx = types.index("plan.awaiting_approval")
        approved_idx = types.index("plan.approved")
        first_step = types.index("plan.step_start")
        done_idx = len(types) - 1 - types[::-1].index("done")

        assert status_idx < created_idx < awaiting_idx < approved_idx < first_step < done_idx


# ──────────────────────────────────────────────────────────────────────
# ReAct loop tests: Reflect, Thinking extraction, Sense context building
# ──────────────────────────────────────────────────────────────────────

class TestReflect:
    """Tests for the static _reflect validation method."""

    def test_empty_output_fails(self):
        step = PlanStep(index=0, description="Do something", task_type="coding")
        passed, reason = Orchestrator._reflect(step, "")
        assert not passed
        assert reason == "Empty output"

    def test_none_output_fails(self):
        step = PlanStep(index=0, description="Do something", task_type="general")
        passed, reason = Orchestrator._reflect(step, None)
        assert not passed
        assert reason == "Empty output"

    def test_whitespace_output_fails(self):
        step = PlanStep(index=0, description="Do something", task_type="coding")
        passed, reason = Orchestrator._reflect(step, "   \n  ")
        assert not passed
        assert reason == "Empty output"

    def test_error_output_fails(self):
        step = PlanStep(index=0, description="Do something", task_type="coding")
        passed, reason = Orchestrator._reflect(step, "[Error executing step: timeout]")
        assert not passed
        assert reason == "Execution error"

    def test_short_output_fails_for_substantive_types(self):
        for task_type in ("coding", "creative", "analysis", "reasoning"):
            step = PlanStep(index=0, description="Do something", task_type=task_type)
            passed, reason = Orchestrator._reflect(step, "OK")
            assert not passed, f"Should fail for {task_type}"
            assert reason == "Output too short for task type"

    def test_short_output_ok_for_general(self):
        step = PlanStep(index=0, description="Do something", task_type="general")
        passed, reason = Orchestrator._reflect(step, "OK")
        assert passed
        assert reason == "OK"

    def test_good_output_passes(self):
        step = PlanStep(index=0, description="Write code", task_type="coding")
        passed, reason = Orchestrator._reflect(step, "def hello():\n    print('hello world')")
        assert passed
        assert reason == "OK"


class TestReactReflectRetry:
    """Tests that a failing step is retried once by the ReAct loop."""

    @pytest.mark.asyncio
    async def test_retry_on_empty_output(self):
        """When execute_step returns empty, it should be retried once."""
        call_count = 0

        async def failing_then_success(self, step, context="", images=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return StepResult(text="", reasoning="")
            return StepResult(text="Valid output after retry", reasoning="")

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )

        import types as _types
        orch.execute_step = _types.MethodType(failing_then_success, orch)

        _patch_plan(orch, [
            PlanStep(index=0, description="single task", task_type="coding"),
        ])

        events = []
        async for event in orch.run(
            messages=[ChatMessage(role="user", content="test")],
            metadata={"chat_id": "react-1"},
            require_approval=False,
        ):
            events.append(event)

        assert call_count == 2, "Step should be executed twice (1 initial + 1 retry)"

        reflect_events = [e for e in events if e["type"] == "plan.step_reflect"]
        assert len(reflect_events) == 2
        assert not reflect_events[0]["passed"]
        assert reflect_events[0]["retrying"] is True
        assert reflect_events[1]["passed"]
        assert reflect_events[1]["retrying"] is False

    @pytest.mark.asyncio
    async def test_no_retry_when_passes(self):
        """When the step passes validation, no retry should occur."""
        call_count = 0

        async def always_success(self, step, context="", images=None):
            nonlocal call_count
            call_count += 1
            return StepResult(text="Good result with enough content", reasoning="")

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )

        import types as _types
        orch.execute_step = _types.MethodType(always_success, orch)

        _patch_plan(orch, [
            PlanStep(index=0, description="single task", task_type="general"),
        ])

        async for _ in orch.run(
            messages=[ChatMessage(role="user", content="test")],
            metadata={"chat_id": "react-2"},
            require_approval=False,
        ):
            pass

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_max_one_retry(self):
        """Even if retry also fails, we only retry once."""
        call_count = 0

        async def always_empty(self, step, context="", images=None):
            nonlocal call_count
            call_count += 1
            return StepResult(text="", reasoning="")

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )

        import types as _types
        orch.execute_step = _types.MethodType(always_empty, orch)

        _patch_plan(orch, [
            PlanStep(index=0, description="single task", task_type="coding"),
        ])

        events = []
        async for event in orch.run(
            messages=[ChatMessage(role="user", content="test")],
            metadata={"chat_id": "react-3"},
            require_approval=False,
        ):
            events.append(event)

        assert call_count == 2, "Should try exactly twice (initial + 1 retry)"

        reflect_events = [e for e in events if e["type"] == "plan.step_reflect"]
        assert len(reflect_events) == 2
        assert not reflect_events[0]["passed"]
        assert not reflect_events[1]["passed"]


class TestReactThinking:
    """Tests that reasoning_content is captured and yielded as events."""

    @pytest.mark.asyncio
    async def test_thinking_event_emitted(self):
        """When execute_step returns reasoning, a plan.step_thinking event is yielded."""

        async def reasoning_executor(self, step, context="", images=None):
            return StepResult(
                text="The answer is 42",
                reasoning="Let me think about this step by step...",
            )

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )

        import types as _types
        orch.execute_step = _types.MethodType(reasoning_executor, orch)

        _patch_plan(orch, [
            PlanStep(index=0, description="reason about this", task_type="reasoning"),
        ])

        events = []
        async for event in orch.run(
            messages=[ChatMessage(role="user", content="test")],
            metadata={"chat_id": "think-1"},
            require_approval=False,
        ):
            events.append(event)

        thinking_events = [e for e in events if e["type"] == "plan.step_thinking"]
        assert len(thinking_events) == 1
        assert "step by step" in thinking_events[0]["content"]
        assert thinking_events[0]["index"] == 0

    @pytest.mark.asyncio
    async def test_no_thinking_event_when_empty(self):
        """When reasoning is empty, no plan.step_thinking event is yielded."""

        async def no_reasoning_executor(self, step, context="", images=None):
            return StepResult(text="Plain answer", reasoning="")

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )

        import types as _types
        orch.execute_step = _types.MethodType(no_reasoning_executor, orch)

        _patch_plan(orch, [
            PlanStep(index=0, description="task", task_type="general"),
        ])

        events = []
        async for event in orch.run(
            messages=[ChatMessage(role="user", content="test")],
            metadata={"chat_id": "think-2"},
            require_approval=False,
        ):
            events.append(event)

        thinking_events = [e for e in events if e["type"] == "plan.step_thinking"]
        assert len(thinking_events) == 0


class TestReactSense:
    """Tests for the SENSE phase — _build_step_context."""

    @pytest.mark.asyncio
    async def test_baseline_context_always_has_user_request(self):
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        step = PlanStep(index=0, description="Do something", task_type="coding")
        ctx = await orch._build_step_context(step, "Write me a poem", {}, [])
        assert "Write me a poem" in ctx

    @pytest.mark.asyncio
    async def test_dependency_results_included(self):
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        step = PlanStep(index=1, description="Step 2", task_type="creative", depends_on=[0])
        completed = {0: "Hello world program in Python"}
        ctx = await orch._build_step_context(step, "user request", completed, [])
        assert "Hello world program in Python" in ctx
        assert "Result from step 1" in ctx

    @pytest.mark.asyncio
    async def test_no_dependency_results_for_independent_step(self):
        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )
        step = PlanStep(index=0, description="Step 1", task_type="coding")
        ctx = await orch._build_step_context(step, "user request", {}, [])
        assert "Result from step" not in ctx

    @pytest.mark.asyncio
    async def test_phase_events_emitted_during_execution(self):
        """The run loop should emit phase events (sense → act → reflect) per step."""

        async def simple_executor(self, step, context="", images=None):
            return StepResult(text="Valid output here", reasoning="")

        orch = Orchestrator(
            model_registry=FakeRegistry(),
            task_router=FakeRouter(),
        )

        import types as _types
        orch.execute_step = _types.MethodType(simple_executor, orch)

        _patch_plan(orch, [
            PlanStep(index=0, description="task", task_type="general"),
        ])

        events = []
        async for event in orch.run(
            messages=[ChatMessage(role="user", content="test")],
            metadata={"chat_id": "sense-4"},
            require_approval=False,
        ):
            events.append(event)

        phase_events = [e for e in events if e["type"] == "phase"]
        phases = [e["phase"] for e in phase_events]
        assert phases == ["sense", "act", "reflect"]


class TestOllamaReasoning:
    """Tests for API-verified thinking capability detection."""

    def test_reasoning_enabled_when_in_cache(self):
        from klaus.models.backends.ollama import OllamaBackend
        backend = OllamaBackend()
        backend._thinking_models.add("qwen3:14b")
        model = backend.get_chat_model("qwen3:14b")
        assert getattr(model, "reasoning", False) is True

    def test_reasoning_not_enabled_when_not_in_cache(self):
        from klaus.models.backends.ollama import OllamaBackend
        backend = OllamaBackend()
        model = backend.get_chat_model("qwen3:14b")
        assert getattr(model, "reasoning", None) is not True

    def test_reasoning_not_enabled_for_unknown_model(self):
        from klaus.models.backends.ollama import OllamaBackend
        backend = OllamaBackend()
        model = backend.get_chat_model("llama3.2:latest")
        assert getattr(model, "reasoning", None) is not True

    def test_explicit_reasoning_false_overrides_cache(self):
        from klaus.models.backends.ollama import OllamaBackend
        backend = OllamaBackend()
        backend._thinking_models.add("qwen3:14b")
        model = backend.get_chat_model("qwen3:14b", reasoning=False)
        assert getattr(model, "reasoning", True) is False


class TestStepResult:
    """Tests for the StepResult dataclass."""

    def test_defaults(self):
        r = StepResult(text="hello")
        assert r.text == "hello"
        assert r.reasoning == ""

    def test_with_reasoning(self):
        r = StepResult(text="answer", reasoning="thinking...")
        assert r.reasoning == "thinking..."


def _patch_plan(orch: Orchestrator, steps: list[PlanStep]):
    """Monkey-patch orch.plan to return fixed steps."""
    import types as _types

    async def simple_plan(self, user_input, has_images=False):
        return steps

    orch.plan = _types.MethodType(simple_plan, orch)
