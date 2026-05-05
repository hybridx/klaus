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
from langgraph.prebuilt import create_react_agent

from klaus.agents.md_agents import AgentSpec
from klaus.agents.tracing import get_langfuse_handler
from klaus.models.base import ChatMessage
from klaus.routing.router import classify_task

if TYPE_CHECKING:
    from klaus.memory.store import MemoryManager
    from klaus.models.registry import ModelRegistry
    from klaus.routing.router import TaskRouter
    from klaus.superpowers.registry import SuperpowerRegistry

logger = logging.getLogger(__name__)


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


class OrchestratorState(TypedDict):
    messages: list
    user_input: str
    plan: list[dict]
    results: Annotated[list[dict], operator.add]
    final_response: str
    chat_id: str


def _build_planner_prompt(agents: list[AgentSpec], corrections: str = "") -> str:
    """Build the planner system prompt, including available specialist agents."""
    parts = [
        "You are a task planner. Given a user request, decompose it into a list "
        "of independent sub-tasks.\n\n"
        "Return ONLY a JSON array where each element has:\n"
        '- "description": what to do\n'
        '- "task_type": one of "coding", "creative", "reasoning", '
        '"analysis", "summarization", or "general"\n'
        '- "depends_on": array of step indices this depends on (empty if independent)\n'
    ]

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
        "\n\nIf the request is simple and needs only one step, return a single-element array.\n"
        "Do NOT include any text outside the JSON array. Return valid JSON only."
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

    async def plan(self, user_input: str) -> list[PlanStep]:
        """Use the planner model to decompose a request into steps."""
        corrections = await self._load_corrections(user_input)
        prompt = _build_planner_prompt(self._agents, corrections)

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

        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Planner returned invalid JSON, treating as single task")
            return [PlanStep(
                index=0,
                description=user_input,
                task_type=classify_task(user_input) or "general",
            )]

        if not isinstance(raw, list):
            raw = [raw]

        steps = []
        for i, item in enumerate(raw):
            steps.append(PlanStep(
                index=i,
                description=item.get("description", user_input),
                task_type=item.get("task_type", "general"),
                agent=item.get("agent"),
                depends_on=item.get("depends_on", []),
            ))
        return steps

    def resolve_step(self, step: PlanStep) -> PlanStep:
        """Resolve which backend/model to use for a plan step.

        If a specialist agent is assigned, use its preferred model/backend.
        Otherwise fall back to the task router.
        """
        agent_spec = self._agents_by_name.get(step.agent) if step.agent else None

        if agent_spec and agent_spec.preferred_backend:
            step.backend = agent_spec.preferred_backend
            step.model = agent_spec.preferred_model
        else:
            decision = self._router.resolve(task=step.task_type)
            step.backend = decision.backend
            step.model = decision.model

        if not self._registry.model_supports(step.backend or "", step.model, "tools"):
            fallback = None
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    fallback = loop.run_until_complete(
                        self._registry.find_capable_model(step.backend or "", "tools")
                    )
            except RuntimeError:
                pass
            if fallback:
                step.model = fallback

        return step

    async def execute_step(self, step: PlanStep, context: str = "") -> str:
        """Execute a single plan step using the appropriate agent/model."""
        llm = self._get_executor_llm(step.backend or "", step.model)

        agent_spec = self._agents_by_name.get(step.agent) if step.agent else None
        tool_names = agent_spec.tools if agent_spec else None
        tools = self._collect_tools(tool_names)

        has_tool_support = self._registry.model_supports(
            step.backend or "", step.model, "tools"
        )
        if not has_tool_support:
            tools = []

        system = ""
        if agent_spec and agent_spec.system_prompt:
            system = agent_spec.system_prompt + "\n\n"
        system += f"Task: {step.description}"
        if context:
            system += f"\n\nContext from previous steps:\n{context}"

        agent = create_react_agent(llm, tools, prompt=system)

        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=step.description)]},
        )

        final_messages = result.get("messages", [])
        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content if isinstance(msg.content, str) else str(msg.content)
        return ""

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
        self._approval_event = asyncio.Event()
        self._approval_result = {}
        try:
            await asyncio.wait_for(self._approval_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Plan approval timed out after %.0fs, auto-approving", timeout)
            return {"action": "approve"}
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
        self, user_input: str, original_plan: list[dict], action: str, edits: list[dict], reason: str,
    ) -> None:
        """Store a plan correction in memory so the planner improves over time."""
        if not self._memory:
            return

        import time

        original_desc = "; ".join(s["description"] for s in original_plan)
        edit_desc = ""
        if edits:
            edit_desc = "; ".join(
                f"Step {e.get('index', '?')}: {e.get('description', 'removed' if e.get('remove') else 'edited')}"
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

    async def run(
        self,
        messages: list[ChatMessage],
        metadata: dict[str, Any] | None = None,
        require_approval: bool = True,
    ) -> AsyncIterator[dict]:
        """Run the full orchestration pipeline, yielding events."""
        user_input = " ".join(m.content for m in messages if m.role == "user")
        chat_id = (metadata or {}).get("chat_id", "")

        # Phase 1: Plan
        yield {"type": "status", "step": "planning", "detail": "Creating execution plan..."}
        steps = await self.plan(user_input)

        for step in steps:
            self.resolve_step(step)

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
                yield {"type": "token", "content": "Plan was rejected. Let me know if you'd like me to try a different approach."}
                yield {"type": "done"}
                return

            if action == "edit":
                edits = approval.get("edits", [])
                steps = self._apply_edits(steps, edits)
                for step in steps:
                    self.resolve_step(step)

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

        # Phase 3: Execute each step
        results: list[dict] = []
        completed: dict[int, str] = {}

        for step in steps:
            context_parts = []
            for dep_idx in step.depends_on:
                if dep_idx in completed:
                    context_parts.append(completed[dep_idx])
            context = "\n\n".join(context_parts)

            agent_label = ""
            if step.agent:
                agent_label = f" [{step.agent}]"

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

            try:
                result_text = await self.execute_step(step, context)
            except Exception as exc:
                logger.error("Step %d failed: %s", step.index, exc)
                result_text = f"[Error executing step: {exc}]"

            completed[step.index] = result_text
            results.append({
                "index": step.index,
                "description": step.description,
                "agent": step.agent,
                "result": result_text,
                "backend": step.backend,
                "model": step.model,
            })

            yield {
                "type": "plan.step_done",
                "index": step.index,
                "result_preview": result_text[:200],
                "chat_id": chat_id,
            }

        # Phase 4: Consolidate
        yield {"type": "status", "step": "consolidating", "detail": "Merging results..."}
        final = await self.consolidate(user_input, results)

        yield {
            "type": "plan.consolidated",
            "chat_id": chat_id,
        }

        for token in _chunk_text(final, 20):
            yield {"type": "token", "content": token}

        yield {"type": "done"}


def _chunk_text(text: str, size: int) -> list[str]:
    """Split text into chunks for streaming simulation."""
    chunks = []
    for i in range(0, len(text), size):
        chunks.append(text[i:i + size])
    return chunks
