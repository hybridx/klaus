"""LangGraph agent — ReAct graph with evaluator loop.

Graph: START → worker ⇄ tools → evaluator → (END or worker retry)

The evaluator is a self-critique step that checks response quality against
optional success_criteria. When no criteria are set, it auto-passes with
zero overhead. When criteria are set, it uses structured LLM output to
decide pass/fail, allowing one retry with feedback.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from klaus.agents.tools import collect_mcp_tools
from klaus.agents.tracing import get_langfuse_handler
from klaus.models.base import ChatMessage

if TYPE_CHECKING:
    from klaus.memory.store import MemoryManager
    from klaus.superpowers.registry import SuperpowerRegistry

logger = logging.getLogger(__name__)

_MAX_EVAL_RETRIES = 1


# -- State -------------------------------------------------------------------


class AgentState(TypedDict):
    messages: Annotated[list[Any], add_messages]
    success_criteria: str
    feedback: str
    eval_passed: bool
    eval_retries: int


class EvalResult(BaseModel):
    """Structured evaluator output."""

    feedback: str = Field(description="Brief feedback on the response")
    passed: bool = Field(description="True if the response meets the criteria")
    needs_user_input: bool = Field(
        description="True if user clarification is needed"
    )


# -- Nodes -------------------------------------------------------------------


def _make_worker_node(llm, system_prompt: str):
    def worker(state: AgentState) -> dict:
        messages = list(state["messages"])
        prompt = system_prompt
        fb = state.get("feedback", "")
        if fb:
            prompt += (
                f"\n\nYour previous response was rejected. "
                f"Feedback: {fb}\nPlease improve your response."
            )
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=prompt), *messages]
        return {"messages": [llm.invoke(messages)]}

    return worker


def _make_evaluator_node(llm):
    def evaluator(state: AgentState) -> dict:
        criteria = state.get("success_criteria", "")
        retries = state.get("eval_retries", 0)
        if not criteria or retries >= _MAX_EVAL_RETRIES:
            return {"eval_passed": True}

        last = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                last = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
        if not last:
            return {"eval_passed": True}

        try:
            eval_llm = llm.with_structured_output(EvalResult)
            result = eval_llm.invoke([
                SystemMessage(
                    content="Evaluate if the assistant's response meets the criteria. "
                    "Be lenient for conversational replies. Give the benefit of the doubt."
                ),
                HumanMessage(
                    content=f"Criteria: {criteria}\n\nResponse:\n{last[:2000]}"
                ),
            ])
            if result.passed or result.needs_user_input:
                return {"eval_passed": True}
            logger.info("Evaluator rejected (retry %d): %s", retries, result.feedback)
            return {
                "eval_passed": False,
                "feedback": result.feedback,
                "eval_retries": retries + 1,
            }
        except Exception as exc:
            logger.debug("Evaluator fallback (auto-pass): %s", exc)
            return {"eval_passed": True}

    return evaluator


# -- Routing -----------------------------------------------------------------


def _route_worker(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "evaluator"


def _route_evaluator(state: AgentState) -> str:
    if state.get("eval_passed", True):
        return END
    return "worker"


# -- Build -------------------------------------------------------------------


def build_react_graph(llm, tools: list, system_prompt: str, checkpointer=None):
    """Build: START → worker ⇄ tools → evaluator → (END or worker retry)."""
    builder = StateGraph(AgentState)

    builder.add_node("worker", _make_worker_node(llm, system_prompt))
    builder.add_node("evaluator", _make_evaluator_node(llm))
    if tools:
        builder.add_node("tools", ToolNode(tools=tools))

    builder.add_edge(START, "worker")
    if tools:
        builder.add_conditional_edges(
            "worker", _route_worker, {"tools": "tools", "evaluator": "evaluator"}
        )
        builder.add_edge("tools", "worker")
    else:
        builder.add_edge("worker", "evaluator")

    builder.add_conditional_edges(
        "evaluator", _route_evaluator, {END: END, "worker": "worker"}
    )

    return builder.compile(checkpointer=checkpointer)


# -- Message conversion ------------------------------------------------------

_ROLE_MAP = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}


def _to_lc_messages(messages: list[ChatMessage]) -> list:
    result = []
    for m in messages:
        cls = _ROLE_MAP.get(m.role, HumanMessage)
        if m.images and m.role == "user":
            parts: list[dict] = [{"type": "text", "text": m.content}]
            for img_b64 in m.images:
                url = (
                    img_b64
                    if img_b64.startswith("data:")
                    else f"data:image/jpeg;base64,{img_b64}"
                )
                parts.append({"type": "image_url", "image_url": url})
            result.append(HumanMessage(content=parts))
        else:
            result.append(cls(content=m.content))
    return result


# -- System prompt ------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are Klaus, an AI assistant with persistent memory, external tools, "
    "and a self-improving skill system.\n\n"
    "TOOLS: Always prefer calling a tool over guessing. If an MCP tool or "
    "built-in tool can answer the question, call it first.\n\n"
    "MEMORY: Use 'remember' to store facts the user shares (name, preferences, "
    "projects). Use 'search_memory' / 'recall' to retrieve prior context.\n\n"
    "SKILLS: After complex tasks, use 'create_skill' to save the procedure. "
    "Before starting complex tasks, check 'list_skills'. Use 'improve_skill' "
    "when you find a better approach.\n\n"
    "Be concise, helpful, and warm. Use markdown for formatting."
)


def _build_mcp_tool_summary(mcp_manager) -> str:
    all_tools = mcp_manager.get_all_tools()
    if not all_tools:
        return ""
    lines = ["AVAILABLE MCP TOOLS:"]
    for server, tools in all_tools.items():
        if tools:
            lines.append(f"  [{server}]: {', '.join(t.name for t in tools)}")
    lines.append("Use these tools instead of relying on training knowledge.")
    return "\n".join(lines)


# -- klausAgent ---------------------------------------------------------------


class klausAgent:  # noqa: N801
    """LangGraph-powered agent with memory, tools, evaluator, and orchestration."""

    def __init__(
        self,
        model_registry,
        mcp_manager,
        memory: MemoryManager | None = None,
        superpowers: SuperpowerRegistry | None = None,
        db=None,
        task_router=None,
        orchestrator_config=None,
        md_agents=None,
        checkpointer=None,
    ) -> None:
        self._model_registry = model_registry
        self._mcp_manager = mcp_manager
        self._memory = memory
        self._superpowers = superpowers
        self._db = db
        self._task_router = task_router
        self._orchestrator_config = orchestrator_config
        self._md_agents = md_agents or []
        self._active_orchestrator = None
        self._checkpointer = checkpointer

    def _collect_tools(self) -> list:
        if self._superpowers:
            tools = self._superpowers.collect_tools()
            if tools:
                return tools
        return collect_mcp_tools(self._mcp_manager)

    async def _build_memory_context(self, messages: list[ChatMessage]) -> str | None:
        if not self._memory:
            return None
        from klaus.memory.index import MemoryIndex

        index = MemoryIndex(self._memory.tree, db=self._db)
        user_text = " ".join(m.content for m in messages if m.role == "user")
        if not user_text:
            return None
        context = await index.gather_context(user_text)
        return context if context.strip() else None

    def _build_system_prompt(self, memory_context: str | None = None) -> str:
        parts = [_SYSTEM_PROMPT]
        mcp_summary = _build_mcp_tool_summary(self._mcp_manager)
        if mcp_summary:
            parts.append(mcp_summary)
        if memory_context:
            parts.append(f"What you currently remember:\n\n{memory_context}")
        return "\n\n".join(parts)

    def _build_graph(
        self,
        backend=None,
        model=None,
        temperature=0.7,
        memory_context=None,
        use_tools=True,
    ):
        llm = self._model_registry.get_chat_model(
            backend=backend, model=model, temperature=temperature,
        )
        tools = self._collect_tools() if use_tools else []
        prompt = self._build_system_prompt(memory_context)
        logger.debug("Graph built with %d tools", len(tools))
        return build_react_graph(llm, tools, prompt, checkpointer=self._checkpointer)

    def _make_config(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        thread_id = (metadata or {}).get("chat_id", "default")
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        handler = get_langfuse_handler(metadata=metadata)
        if handler:
            config["callbacks"] = [handler]
        return config

    async def invoke(
        self,
        messages: list[ChatMessage],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        memory_context = await self._build_memory_context(messages)
        graph = self._build_graph(backend, model, temperature, memory_context)
        config = self._make_config(metadata)

        user_text = " ".join(m.content for m in messages if m.role == "user")
        input_state = {
            "messages": _to_lc_messages(messages),
            "success_criteria": f"Respond helpfully to: {user_text[:200]}",
        }
        result = await graph.ainvoke(input_state, config=config)

        content = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                content = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
                break

        if self._memory:
            session_id = (metadata or {}).get("chat_id", "default")
            self._memory.put(
                f"/conversations/{session_id}/latest",
                content[:500],
                metadata={"model": model, "backend": backend},
                tags=["conversation"],
            )
            await self._memory.maybe_save()

        return {
            "content": content,
            "messages": result.get("messages", []),
            "model": model,
        }

    async def stream(
        self,
        messages: list[ChatMessage],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        metadata: dict[str, Any] | None = None,
        use_tools: bool = True,
    ) -> AsyncIterator[dict]:
        memory_context = await self._build_memory_context(messages)
        graph = self._build_graph(
            backend, model, temperature, memory_context, use_tools=use_tools,
        )
        config = self._make_config(metadata)
        input_state: dict[str, Any] = {"messages": _to_lc_messages(messages)}

        full_content = ""
        tool_call_count = 0

        async for msg, _ in graph.astream(
            input_state, config=config, stream_mode="messages",
        ):
            if isinstance(msg, ToolMessage):
                text = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
                yield {
                    "type": "tool_result",
                    "name": msg.name or "",
                    "content": text[:1000],
                }

            elif isinstance(msg, AIMessage):
                reasoning = msg.additional_kwargs.get("reasoning_content", "")
                if reasoning:
                    yield {"type": "thinking", "content": reasoning}
                if msg.tool_calls:
                    tool_call_count += len(msg.tool_calls)
                    for tc in msg.tool_calls:
                        yield {
                            "type": "tool_call",
                            "name": tc.get("name", ""),
                            "args": tc.get("args", {}),
                        }
                elif msg.content:
                    token = (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    )
                    full_content += token
                    yield {"type": "token", "content": token}

        if self._memory and full_content:
            session_id = (metadata or {}).get("chat_id", "default")
            self._memory.put(
                f"/conversations/{session_id}/latest",
                full_content[:500],
                metadata={
                    "model": model,
                    "backend": backend,
                    "streamed": True,
                    "tool_calls": tool_call_count,
                },
                tags=["conversation"],
            )
            if tool_call_count >= 3:
                user_text = " ".join(
                    m.content for m in messages if m.role == "user"
                )
                self._memory.put(
                    "/knowledge/system/last_complex_task",
                    content=(
                        f"Complex task ({tool_call_count} tool calls): "
                        f"{user_text[:200]}"
                    ),
                    metadata={"tool_calls": tool_call_count},
                    tags=["nudge", "skill-candidate"],
                )
            await self._memory.maybe_save()

        yield {"type": "done"}

    async def orchestrate(
        self,
        messages: list[ChatMessage],
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict]:
        from klaus.agents.orchestrator import Orchestrator

        if not self._task_router:
            async for event in self.stream(messages=messages, metadata=metadata):
                yield event
            return

        orch_cfg = self._orchestrator_config or {}
        orch = Orchestrator(
            model_registry=self._model_registry,
            task_router=self._task_router,
            superpowers=self._superpowers,
            memory=self._memory,
            planner_backend=orch_cfg.get("planner_backend"),
            planner_model=orch_cfg.get("planner_model"),
            agents=self._md_agents,
        )
        self._active_orchestrator = orch
        async for event in orch.run(messages=messages, metadata=metadata):
            yield event
        self._active_orchestrator = None

        if self._memory:
            user_text = " ".join(
                m.content for m in messages if m.role == "user"
            )
            session_id = (metadata or {}).get("chat_id", "default")
            self._memory.put(
                f"/conversations/{session_id}/latest",
                f"Orchestrated: {user_text[:200]}",
                metadata={"orchestrated": True},
                tags=["conversation", "orchestrated"],
            )
            await self._memory.maybe_save()

    def handle_plan_approval(
        self, action: str, edits: list[dict] | None = None, reason: str = ""
    ) -> bool:
        if self._active_orchestrator:
            self._active_orchestrator.set_approval(action, edits, reason)
            return True
        return False
