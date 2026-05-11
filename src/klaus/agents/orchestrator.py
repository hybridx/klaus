"""Multi-agent orchestrator — planner + human approval + specialist agents + consolidator.

Uses LangGraph StateGraph to decompose complex requests into sub-tasks,
present the plan for human approval, route each to the best-fit specialist
agent, execute them, and consolidate into a single coherent response.
Learns from plan corrections to improve future planning.
"""

from __future__ import annotations

import asyncio
import json
import logging
import operator
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from klaus.agents.graph import build_react_graph
from klaus.agents.md_agents import AgentSpec
from klaus.models.base import ChatMessage
from klaus.routing.router import classify_task

if TYPE_CHECKING:
    from klaus.memory.store import MemoryManager
    from klaus.models.registry import ModelRegistry
    from klaus.routing.router import TaskRouter
    from klaus.superpowers.registry import SuperpowerRegistry

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Return value from execute_step: content + optional reasoning."""
    text: str
    reasoning: str = ""


@dataclass
class PlanStep:
    index: int
    description: str
    task_type: str | None = None
    agent: str | None = None
    depends_on: list[int] = field(default_factory=list)
    backend: str | None = None
    model: str | None = None
    result: str | None = None
    status: str = "pending"
    retries: int = 0


class OrchestratorState(TypedDict):
    messages: list
    user_input: str
    plan: list[dict]
    results: Annotated[list[dict], operator.add]
    final_response: str
    chat_id: str


def _build_planner_prompt(
    agents: list[AgentSpec],
    corrections: str = "",
    has_images: bool = False,
    routing_rules: dict[str, dict] | None = None,
) -> str:
    """Build the planner system prompt with available specialist models and agents."""
    task_types = list(routing_rules.keys()) if routing_rules else []
    task_types_str = ", ".join(f'"{t}"' for t in task_types) if task_types else (
        '"coding", "creative", "reasoning", "analysis", "summarization", "image", "general"'
    )

    parts = [
        "You are a task planner. ALWAYS decompose the user's request into SEPARATE sub-tasks.\n"
        "Each sub-task will be handled by a DIFFERENT specialist model.\n\n"
        "CRITICAL RULES:\n"
        "- You MUST produce MULTIPLE steps — at least one per distinct action the user asked for.\n"
        "- Each step should be a SINGLE focused task, not a combination.\n"
        "- Assign the most specific task_type — never use 'general' if a specific type fits.\n"
        "- Write a clear, self-contained description for each step.\n"
        "- NEVER put the full user message as a single step.\n\n"
        "Return ONLY a JSON array where each element has:\n"
        '- "description": a clear instruction for that specific task (NOT the full user message)\n'
        f'- "task_type": one of {task_types_str}\n'
        '- "depends_on": array of step indices this depends on (empty if independent)\n\n'
        "EXAMPLE:\n"
        'User: "Write a Python script and create a poem about nature"\n'
        "Output:\n"
        "[\n"
        '  {"description": "Write a Python script", "task_type": "coding", "depends_on": []},\n'
        '  {"description": "Create a poem about nature", '
        '"task_type": "creative", "depends_on": []}\n'
        "]\n\n"
        "EXAMPLE:\n"
        'User: "Create hello world code and write a poem about it and describe my image"\n'
        "Output:\n"
        "[\n"
        '  {"description": "Create a hello world program", '
        '"task_type": "coding", "depends_on": []},\n'
        '  {"description": "Write a poem about the hello world program", '
        '"task_type": "creative", "depends_on": [0]},\n'
        '  {"description": "Describe what is in the attached image", '
        '"task_type": "image", "depends_on": []}\n'
        "]\n"
    ]

    if routing_rules:
        parts.append(
            "\nAvailable specialist models "
            "(each task_type routes to a different model):\n"
        )
        for task, rule in routing_rules.items():
            model = rule.get("preferred_model", "default")
            desc = rule.get("description", "")
            line = f'  • "{task}" → {model}'
            if desc:
                line += f" — {desc}"
            parts.append(line)
        parts.append("")

    if has_images:
        parts.append(
            'The user attached images. Steps that analyze/describe the images MUST have '
            'task_type "image". Other steps (code, poems, etc.) MUST use their own task_type.\n'
        )

    if agents:
        parts.append(
            '- "agent": (optional) name of a specialist agent to handle this step\n\n'
            "Available specialist agents:\n"
        )
        for a in agents:
            caps = ", ".join(a.capabilities) if a.capabilities else "general"
            parts.append(f"  • {a.name}: {a.description} (capabilities: {caps})")
        parts.append(
            "\nAssign an agent when its capabilities match the step. "
            "Leave agent empty for general tasks."
        )

    if corrections:
        parts.append(
            "\n\nLEARNED CORRECTIONS — apply these lessons from past plan feedback:\n"
            + corrections
        )

    parts.append(
        "\n\nReturn valid JSON ONLY — no markdown, no explanation, just the array."
    )
    return "\n".join(parts)


class Orchestrator:
    """LangGraph multi-agent orchestrator with human-in-the-loop approval."""

    def __init__(
        self,
        model_registry: ModelRegistry,
        task_router: TaskRouter,
        superpowers: SuperpowerRegistry | None = None,
        memory: MemoryManager | None = None,
        planner_backend: str | None = None,
        planner_model: str | None = None,
        agents: list[AgentSpec] | None = None,
    ) -> None:
        self._registry = model_registry
        self._router = task_router
        self._superpowers = superpowers
        self._memory = memory
        self._planner_backend = planner_backend
        self._planner_model = planner_model
        self._agents = agents or []
        self._agents_by_name: dict[str, AgentSpec] = {a.name: a for a in self._agents}

        self._approval_event: asyncio.Event | None = None
        self._approval_result: dict[str, Any] = {}

    def _get_planner_llm(self):
        return self._registry.get_chat_model(
            backend=self._planner_backend,
            model=self._planner_model,
            temperature=0.3,
        )

    def _get_executor_llm(self, backend: str, model: str | None):
        return self._registry.get_chat_model(
            backend=backend,
            model=model,
            temperature=0.7,
        )

    def _collect_tools(self, tool_names: list[str] | None = None) -> list:
        if not self._superpowers:
            return []
        all_tools = self._superpowers.collect_tools()
        if not tool_names:
            return all_tools
        name_set = set(tool_names)
        return [t for t in all_tools if t.name in name_set]

    async def _load_corrections(self, user_input: str) -> str:
        """Load past plan corrections from memory relevant to this request."""
        if not self._memory:
            return ""

        from klaus.memory.index import MemoryIndex

        index = MemoryIndex(self._memory.tree, db=None)
        results = index.search(
            f"plan correction {user_input[:100]}",
            tags=["plan-correction"],
            max_results=5,
        )
        if not results:
            return ""

        lines = []
        for result in results:
            lines.append(f"• {result.node.content}")
        return "\n".join(lines)

    async def plan(self, user_input: str, has_images: bool = False) -> list[PlanStep]:
        """Use the planner model to decompose a request into steps.

        If the LLM fails to decompose properly (returns 1 step for a multi-part
        request), falls back to the deterministic splitter so we still get
        multiple specialist models involved.
        """
        corrections = await self._load_corrections(user_input)

        routing_rules: dict[str, dict] = {}
        for task, rule in self._router.get_rules().items():
            routing_rules[task] = {
                "preferred_model": rule.preferred_model,
                "description": rule.description,
            }

        prompt = _build_planner_prompt(
            self._agents, corrections,
            has_images=has_images,
            routing_rules=routing_rules or None,
        )

        llm = self._get_planner_llm()
        result = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=user_input),
        ])

        text = result.content if isinstance(result.content, str) else str(result.content)

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            text = text.strip()

        steps: list[PlanStep] = []
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Planner returned invalid JSON — using splitter fallback")
            raw = []

        if not isinstance(raw, list):
            raw = [raw]

        for i, item in enumerate(raw):
            steps.append(PlanStep(
                index=i,
                description=item.get("description", user_input),
                task_type=item.get("task_type", "general"),
                agent=item.get("agent"),
                depends_on=item.get("depends_on", []),
            ))

        if len(steps) <= 1:
            logger.info(
                "Planner returned %d step(s) — falling back to deterministic splitter",
                len(steps),
            )
            steps = self._fallback_split(user_input, has_images)

        return steps

    @staticmethod
    def _fallback_split(user_input: str, has_images: bool = False) -> list[PlanStep]:
        """Deterministic decomposition when the LLM planner fails to split."""
        from klaus.routing.splitter import split_tasks

        subtasks = split_tasks(user_input)

        if has_images:
            has_image_step = any(
                st.task_type == "image" for st in subtasks
            )
            if not has_image_step:
                subtasks.append(
                    type(subtasks[0])(
                        index=len(subtasks),
                        text="Describe what is in the attached image",
                        task_type="image",
                    )
                )

        steps = []
        for i, st in enumerate(subtasks):
            steps.append(PlanStep(
                index=i,
                description=st.text,
                task_type=st.task_type or classify_task(st.text) or "general",
            ))
        return steps

    async def resolve_step_async(self, step: PlanStep) -> PlanStep:
        """Resolve which backend/model to use for a plan step."""
        agent_spec = self._agents_by_name.get(step.agent) if step.agent else None

        if agent_spec and agent_spec.preferred_backend:
            step.backend = agent_spec.preferred_backend
            step.model = agent_spec.preferred_model
        else:
            decision = self._router.resolve(task=step.task_type)
            step.backend = decision.backend
            step.model = decision.model

        if step.task_type == "image":
            if not self._registry.model_supports(step.backend or "", step.model, "vision"):
                vm = await self._registry.find_capable_model(step.backend or "", "vision")
                if vm:
                    step.model = vm
                else:
                    for bname in self._registry.list_backends():
                        if bname == step.backend:
                            continue
                        vm = await self._registry.find_capable_model(bname, "vision")
                        if vm:
                            step.backend = bname
                            step.model = vm
                            break
                logger.info(
                    "Image step %d → vision model %s on %s",
                    step.index,
                    step.model,
                    step.backend,
                )
        elif not self._registry.model_supports(step.backend or "", step.model, "tools"):
            fallback = await self._registry.find_capable_model(step.backend or "", "tools")
            if fallback:
                step.model = fallback

        return step

    async def execute_step(
        self, step: PlanStep, context: str = "", images: list[str] | None = None,
    ) -> StepResult:
        """Execute a single plan step using the appropriate agent/model.

        Returns a StepResult with the content and any chain-of-thought reasoning
        extracted from the model's response.
        """
        llm = self._get_executor_llm(step.backend or "", step.model)

        agent_spec = self._agents_by_name.get(step.agent) if step.agent else None
        tool_names = agent_spec.tools if agent_spec else None

        use_tools = step.task_type != "image"
        tools = self._collect_tools(tool_names) if use_tools else []

        if tools and not self._registry.model_supports(
            step.backend or "", step.model, "tools"
        ):
            tools = []

        system = ""
        if agent_spec and agent_spec.system_prompt:
            system = agent_spec.system_prompt + "\n\n"
        if tools:
            tool_list = ", ".join(t.name for t in tools)
            system += (
                f"You have these tools available: {tool_list}\n"
                "ALWAYS use a tool when it can answer the question — "
                "never guess when a tool can provide real data.\n\n"
            )
        system += f"Task: {step.description}"
        if context:
            system += f"\n\nContext from previous steps:\n{context}"

        agent = build_react_graph(llm, tools, system)

        step_images = images if (step.task_type == "image" and images) else None
        if step_images:
            parts: list[dict] = [{"type": "text", "text": step.description}]
            for img_b64 in step_images:
                data_url = (
                    img_b64 if img_b64.startswith("data:")
                    else f"data:image/jpeg;base64,{img_b64}"
                )
                parts.append({"type": "image_url", "image_url": data_url})
            user_msg = HumanMessage(content=parts)
        else:
            user_msg = HumanMessage(content=step.description)

        result = await agent.ainvoke(
            {"messages": [user_msg]},
        )

        final_messages = result.get("messages", [])
        content = ""
        reasoning_parts: list[str] = []

        for msg in final_messages:
            if isinstance(msg, AIMessage):
                rc = msg.additional_kwargs.get("reasoning_content", "")
                if rc:
                    reasoning_parts.append(rc)

        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage) and msg.content:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        return StepResult(text=content, reasoning="\n".join(reasoning_parts))

    async def consolidate(self, user_input: str, results: list[dict]) -> str:
        """Merge results from all executors into a coherent response."""
        if len(results) == 1:
            return results[0].get("result", "")

        results_text = "\n\n".join(
            f"--- Step {r['index'] + 1}: {r['description']} ---\n{r['result']}"
            for r in results
        )

        prompt = (
            "You are a response consolidator. Synthesize these sub-task results "
            "into a single coherent, well-formatted response. Do not mention the "
            "internal task decomposition.\n\n"
            f"User's original request: {user_input}\n\n"
            f"Sub-task results:\n{results_text}\n\n"
            "Provide a unified response:"
        )

        llm = self._get_planner_llm()
        result = await llm.ainvoke([HumanMessage(content=prompt)])

        text = result.content if isinstance(result.content, str) else str(result.content)
        return text

    def prepare_for_approval(self) -> None:
        """Create the approval event BEFORE yielding 'awaiting_approval' to the UI.

        This prevents a race where set_approval fires between the yield and
        _wait_for_approval, losing the user's response.
        """
        self._approval_event = asyncio.Event()
        self._approval_result = {}

    def set_approval(self, action: str, edits: list[dict] | None = None, reason: str = "") -> None:
        """Called from the REST handler when the user approves/rejects/edits the plan."""
        self._approval_result = {
            "action": action,
            "edits": edits or [],
            "reason": reason,
        }
        if self._approval_event:
            self._approval_event.set()

    async def _wait_for_approval(self, timeout: float = 300.0) -> dict[str, Any]:
        """Block until the user approves, rejects, or edits the plan."""
        if not self._approval_event:
            self._approval_event = asyncio.Event()
            self._approval_result = {}
        try:
            await asyncio.wait_for(self._approval_event.wait(), timeout=timeout)
        except TimeoutError:
            logger.warning("Plan approval timed out after %.0fs, auto-approving", timeout)
            return {"action": "approve"}
        finally:
            self._approval_event = None
        return self._approval_result

    def _apply_edits(self, steps: list[PlanStep], edits: list[dict]) -> list[PlanStep]:
        """Apply user edits to the plan steps."""
        edit_map = {e["index"]: e for e in edits if "index" in e}
        new_steps: list[PlanStep] = []
        for step in steps:
            if step.index in edit_map:
                edit = edit_map[step.index]
                if edit.get("remove"):
                    continue
                if "description" in edit:
                    step.description = edit["description"]
                if "task_type" in edit:
                    step.task_type = edit["task_type"]
                if "agent" in edit:
                    step.agent = edit["agent"]
            new_steps.append(step)

        for i, s in enumerate(new_steps):
            s.index = i
        return new_steps

    async def _store_correction(
        self,
        user_input: str,
        original_plan: list[dict],
        action: str,
        edits: list[dict],
        reason: str,
    ) -> None:
        """Store a plan correction in memory so the planner improves over time."""
        if not self._memory:
            return

        import time

        original_desc = "; ".join(s["description"] for s in original_plan)
        edit_desc = ""
        if edits:
            edit_desc = "; ".join(
                (
                    f"Step {e.get('index', '?')}: "
                    f"{e.get('description', 'removed' if e.get('remove') else 'edited')}"
                )
                for e in edits
            )

        content = (
            f"Request: {user_input[:200]}\n"
            f"Original plan: {original_desc[:300]}\n"
            f"Action: {action}\n"
        )
        if edit_desc:
            content += f"Edits: {edit_desc}\n"
        if reason:
            content += f"Reason: {reason}\n"

        path = f"/knowledge/plan_corrections/{int(time.time())}"
        self._memory.put(
            path,
            content,
            metadata={"action": action, "request_preview": user_input[:100]},
            tags=["plan-correction"],
        )
        await self._memory.maybe_save()
        logger.info("Stored plan correction: %s", action)

    async def _build_step_context(
        self,
        step: PlanStep,
        user_input: str,
        completed: dict[int, str],
        images: list[str],
    ) -> str:
        """SENSE: gather rich context for a step before execution.

        Combines dependency results, relevant memory, and the original user
        intent so the specialist model has full situational awareness.
        """
        parts: list[str] = []

        for dep_idx in step.depends_on:
            if dep_idx in completed:
                parts.append(f"Result from step {dep_idx + 1}:\n{completed[dep_idx]}")

        if self._memory:
            try:
                from klaus.memory.index import MemoryIndex
                idx = MemoryIndex(self._memory.tree, db=None)
                results = idx.search(step.description, max_results=2)
                for r in results:
                    parts.append(f"Relevant knowledge: {r.node.content[:200]}")
            except Exception:
                pass

        parts.append(f"Original user request: {user_input[:300]}")

        return "\n\n".join(parts)

    @staticmethod
    def _reflect(step: PlanStep, result_text: str) -> tuple[bool, str]:
        """REFLECT: validate step output quality.

        Returns (passed, reason). A failing reflection triggers one retry.
        """
        if not result_text or not result_text.strip():
            return False, "Empty output"
        if result_text.startswith("[Error"):
            return False, "Execution error"
        substantive_types = ("coding", "creative", "analysis", "reasoning")
        if len(result_text.strip()) < 20 and step.task_type in substantive_types:
            return False, "Output too short for task type"
        return True, "OK"

    async def run(
        self,
        messages: list[ChatMessage],
        metadata: dict[str, Any] | None = None,
        require_approval: bool = True,
    ) -> AsyncIterator[dict]:
        """Run the full orchestration pipeline, yielding events."""
        user_input = " ".join(m.content for m in messages if m.role == "user")
        chat_id = (metadata or {}).get("chat_id", "")

        images: list[str] = []
        for m in messages:
            if m.role == "user" and m.images:
                images.extend(m.images)

        # Phase 1: Plan
        yield {"type": "status", "step": "planning", "detail": "Creating execution plan..."}
        steps = await self.plan(user_input, has_images=bool(images))

        for step in steps:
            await self.resolve_step_async(step)

        plan_data = [
            {
                "index": s.index,
                "description": s.description,
                "task_type": s.task_type,
                "agent": s.agent,
                "backend": s.backend,
                "model": s.model,
                "depends_on": s.depends_on,
            }
            for s in steps
        ]

        yield {
            "type": "plan.created",
            "plan": plan_data,
            "agents": [
                {"name": a.name, "description": a.description, "capabilities": a.capabilities}
                for a in self._agents
            ],
            "chat_id": chat_id,
        }

        # Phase 2: Wait for human approval
        if require_approval:
            self.prepare_for_approval()
            yield {
                "type": "plan.awaiting_approval",
                "chat_id": chat_id,
            }

            approval = await self._wait_for_approval()
            action = approval.get("action", "approve")

            if action == "reject":
                yield {
                    "type": "plan.rejected",
                    "reason": approval.get("reason", ""),
                    "chat_id": chat_id,
                }
                await self._store_correction(
                    user_input, plan_data, "reject", [], approval.get("reason", ""),
                )
                yield {
                    "type": "token",
                    "content": (
                        "Plan was rejected. Let me know if you'd like me to try a "
                        "different approach."
                    ),
                }
                yield {"type": "done"}
                return

            if action == "edit":
                edits = approval.get("edits", [])
                steps = self._apply_edits(steps, edits)
                for step in steps:
                    await self.resolve_step_async(step)

                await self._store_correction(
                    user_input, plan_data, "edit", edits, approval.get("reason", ""),
                )

                yield {
                    "type": "plan.revised",
                    "plan": [
                        {
                            "index": s.index,
                            "description": s.description,
                            "task_type": s.task_type,
                            "agent": s.agent,
                            "backend": s.backend,
                            "model": s.model,
                            "depends_on": s.depends_on,
                        }
                        for s in steps
                    ],
                    "chat_id": chat_id,
                }
            else:
                yield {
                    "type": "plan.approved",
                    "chat_id": chat_id,
                }

        # Phase 3: ReAct loop — Sense → Act → Reflect per step
        completed: dict[int, str] = {}

        for step in steps:
            # ── SENSE ─────────────────────────────────────────────
            yield {
                "type": "phase", "phase": "sense",
                "index": step.index, "chat_id": chat_id,
            }
            context = await self._build_step_context(
                step, user_input, completed, images,
            )

            yield {
                "type": "plan.step_start",
                "index": step.index,
                "description": step.description,
                "task_type": step.task_type,
                "agent": step.agent,
                "backend": step.backend,
                "model": step.model,
                "chat_id": chat_id,
            }

            # ── ACT ──────────────────────────────────────────────
            yield {
                "type": "phase", "phase": "act",
                "index": step.index, "chat_id": chat_id,
            }

            try:
                result = await self.execute_step(step, context, images=images or None)
            except Exception as exc:
                logger.error("Step %d failed: %s", step.index, exc)
                result = StepResult(text=f"[Error executing step: {exc}]")

            if result.reasoning:
                yield {
                    "type": "plan.step_thinking",
                    "index": step.index,
                    "content": result.reasoning[:2000],
                    "chat_id": chat_id,
                }

            # ── REFLECT ──────────────────────────────────────────
            yield {
                "type": "phase", "phase": "reflect",
                "index": step.index, "chat_id": chat_id,
            }
            passed, reason = self._reflect(step, result.text)

            if not passed and step.retries < 1:
                yield {
                    "type": "plan.step_reflect",
                    "index": step.index, "passed": False,
                    "reason": reason, "retrying": True,
                    "chat_id": chat_id,
                }
                step.retries += 1
                retry_context = (
                    context
                    + f"\n\nPrevious attempt failed: {reason}. Try again carefully."
                )
                try:
                    result = await self.execute_step(
                        step, retry_context, images=images or None,
                    )
                except Exception as exc:
                    logger.error("Step %d retry failed: %s", step.index, exc)
                    result = StepResult(text=f"[Error on retry: {exc}]")

                passed, reason = self._reflect(step, result.text)

            yield {
                "type": "plan.step_reflect",
                "index": step.index, "passed": passed,
                "reason": reason, "retrying": False,
                "chat_id": chat_id,
            }

            completed[step.index] = result.text

            yield {
                "type": "plan.step_done",
                "index": step.index,
                "result": result.text,
                "result_preview": result.text[:200],
                "backend": step.backend,
                "model": step.model,
                "task_type": step.task_type,
                "chat_id": chat_id,
            }

        yield {"type": "done"}


def _chunk_text(text: str, size: int) -> list[str]:
    """Split text into chunks for streaming simulation."""
    chunks = []
    for i in range(0, len(text), size):
        chunks.append(text[i:i + size])
    return chunks
