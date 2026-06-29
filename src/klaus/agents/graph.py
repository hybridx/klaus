"""Deep Agents powered agent — replaces the manual LangGraph ReAct graph.

Uses `create_deep_agent` from the Deep Agents SDK for the core agent loop
(planning, tool calling, context management, subagent spawning).

Klaus adds on top:
  - MCP server tools exposed as a dedicated subagent
  - Multi-model routing via the TaskRouter
  - Memory context injection
  - SSE streaming adapter for the web UI
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from klaus.agents.tools import collect_mcp_tools
from klaus.agents.tracing import get_langfuse_handler
from klaus.models.base import ChatMessage

if TYPE_CHECKING:
    from klaus.memory.store import MemoryManager
    from klaus.superpowers.registry import SuperpowerRegistry

logger = logging.getLogger(__name__)


# -- Message conversion -------------------------------------------------------

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


# -- System prompt -------------------------------------------------------------

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


# -- MCP subagent builder -----------------------------------------------------


def _build_mcp_subagent(mcp_manager) -> dict | None:
    """Create a dedicated subagent with all connected MCP server tools.

    Context isolation: the main agent delegates MCP lookups to this specialist,
    keeping its own context window clean.
    """
    tools = collect_mcp_tools(mcp_manager)
    if not tools:
        return None

    server_names = [
        name for name, ts in mcp_manager.get_all_tools().items() if ts
    ]
    servers_desc = ", ".join(server_names) if server_names else "external services"

    return {
        "name": "mcp-agent",
        "description": (
            f"Specialist with access to connected external services ({servers_desc}) "
            "via MCP servers. Delegate to this agent for any external data lookup, "
            "API query, or action on third-party platforms."
        ),
        "system_prompt": (
            "You have access to MCP server tools. Use them to answer questions "
            "and perform actions on external services. Always call the most "
            "specific tool available. Return results clearly and concisely."
        ),
        "tools": tools,
    }


# -- klausAgent ---------------------------------------------------------------


class klausAgent:  # noqa: N801
    """Deep Agents powered assistant with memory, MCP, tools, and orchestration."""

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

    def _build_agent(
        self,
        backend=None,
        model=None,
        temperature=0.7,
        memory_context=None,
        use_tools=True,
    ):
        """Build a Deep Agent graph for a single request."""
        llm = self._model_registry.get_chat_model(
            backend=backend, model=model, temperature=temperature,
        )
        tools = self._collect_tools() if use_tools else []
        prompt = self._build_system_prompt(memory_context)

        subagents = []
        mcp_sub = _build_mcp_subagent(self._mcp_manager)
        if mcp_sub:
            subagents.append(mcp_sub)

        logger.debug(
            "Deep Agent built: %d tools, %d subagents",
            len(tools), len(subagents),
        )

        return create_deep_agent(
            model=llm,
            tools=tools,
            system_prompt=prompt,
            subagents=subagents or None,
            checkpointer=self._checkpointer,
            name="klaus",
        )

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
        agent = self._build_agent(backend, model, temperature, memory_context)
        config = self._make_config(metadata)

        input_state = {"messages": _to_lc_messages(messages)}
        result = await agent.ainvoke(input_state, config=config)

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
        """Stream tokens via the Deep Agent, adapting events to Klaus SSE protocol."""
        memory_context = await self._build_memory_context(messages)
        agent = self._build_agent(
            backend, model, temperature, memory_context, use_tools=use_tools,
        )
        config = self._make_config(metadata)
        input_state: dict[str, Any] = {"messages": _to_lc_messages(messages)}

        full_content = ""
        tool_call_count = 0

        async for msg, _ in agent.astream(
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
