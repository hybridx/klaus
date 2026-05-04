"""LangGraph agent — ReAct agent with memory, superpowers, and Langfuse tracing."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from klaus.agents.tools import collect_mcp_tools
from klaus.agents.tracing import get_langfuse_handler
from klaus.models.base import ChatMessage

if TYPE_CHECKING:
    from klaus.memory.store import MemoryManager
    from klaus.superpowers.registry import SuperpowerRegistry

logger = logging.getLogger(__name__)

_ROLE_MAP = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


def _to_lc_messages(messages: list[ChatMessage]) -> list:
    result = []
    for m in messages:
        cls = _ROLE_MAP.get(m.role, HumanMessage)
        if m.images and m.role == "user":
            parts: list[dict] = [{"type": "text", "text": m.content}]
            for img_b64 in m.images:
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                })
            result.append(HumanMessage(content=parts))
        else:
            result.append(cls(content=m.content))
    return result


class klausAgent:  # noqa: N801
    """A LangGraph-powered agent with memory tree and superpower tools.

    The agent is rebuilt per-request so it always has the latest tool set,
    the correct model, and fresh memory context injected as a system message.
    """

    def __init__(
        self,
        model_registry,
        mcp_manager,
        memory: MemoryManager | None = None,
        superpowers: SuperpowerRegistry | None = None,
        db=None,
    ) -> None:
        self._model_registry = model_registry
        self._mcp_manager = mcp_manager
        self._memory = memory
        self._superpowers = superpowers
        self._db = db

    def _collect_tools(self) -> list:
        """Gather tools from superpowers first, fall back to raw MCP tools."""
        if self._superpowers:
            tools = self._superpowers.collect_tools()
            if tools:
                return tools

        return collect_mcp_tools(self._mcp_manager)

    async def _build_memory_context(self, messages: list[ChatMessage]) -> str | None:
        """Extract relevant memory context for the current conversation."""
        if not self._memory:
            return None

        from klaus.memory.index import MemoryIndex

        index = MemoryIndex(self._memory.tree, db=self._db)

        user_text = " ".join(m.content for m in messages if m.role == "user")
        if not user_text:
            return None

        context = await index.gather_context(user_text)
        return context if context.strip() else None

    _SYSTEM_PROMPT = (
        "You are Klaus, a personal AI assistant with persistent memory and "
        "a self-improving skill system. You remember things across conversations "
        "and continuously build knowledge about the user and the world.\n\n"
        "MEMORY — Always be learning:\n"
        "• When the user shares their name, preferences, interests, or any fact, "
        "use 'remember' to store it (e.g. remember(path='user/name', content='Deepesh')).\n"
        "• Before answering questions that might relate to past conversations, "
        "use 'search_memory' to check what you already know.\n"
        "• Use 'recall' to retrieve a specific memory by path.\n"
        "• Proactively remember useful context: project names, tech stacks, "
        "recurring topics, user communication style.\n\n"
        "SKILLS — Learn from experience:\n"
        "• After completing a complex multi-step task, use 'create_skill' to save "
        "the procedure so you can reuse it.\n"
        "• Before starting a complex task, use 'list_skills' to check if you've "
        "solved something similar before.\n"
        "• After using a skill, if you found a better approach, use 'improve_skill' "
        "to make it better for next time.\n\n"
        "IMAGE GENERATION:\n"
        "• When the user asks you to create, draw, or generate an image, use the "
        "'generate_image' tool with a detailed descriptive prompt.\n\n"
        "Be concise, helpful, and warm. Format responses with markdown when useful."
    )

    def _build_agent(
        self,
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        memory_context: str | None = None,
    ):
        llm = self._model_registry.get_chat_model(
            backend=backend,
            model=model,
            temperature=temperature,
        )

        tools = self._collect_tools()

        parts = [self._SYSTEM_PROMPT]
        if memory_context:
            parts.append(
                f"Here is what you currently remember:\n\n{memory_context}"
            )
        prompt = "\n\n".join(parts)

        if tools:
            logger.debug("Agent built with %d tools", len(tools))

        return create_react_agent(llm, tools, prompt=prompt)

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
        lc_messages = _to_lc_messages(messages)

        config: dict[str, Any] = {}
        langfuse_handler = get_langfuse_handler(metadata=metadata)
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]

        result = await agent.ainvoke(
            {"messages": lc_messages},
            config=config,
        )

        final_messages = result.get("messages", [])
        content = ""
        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage) and msg.content:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        # Store the interaction in conversation memory
        if self._memory:
            session_id = (metadata or {}).get("chat_id", "default")
            self._memory.put(
                f"/conversations/{session_id}/latest",
                content[:500],
                metadata={"model": model, "backend": backend},
                tags=["conversation"],
            )

        # Auto-save if needed
        if self._memory:
            await self._memory.maybe_save()

        return {
            "content": content,
            "messages": final_messages,
            "model": model,
        }

    async def stream(
        self,
        messages: list[ChatMessage],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict]:
        """Stream agent execution — yields events for each step."""
        memory_context = await self._build_memory_context(messages)
        agent = self._build_agent(backend, model, temperature, memory_context)
        lc_messages = _to_lc_messages(messages)

        config: dict[str, Any] = {"stream_mode": "messages"}
        langfuse_handler = get_langfuse_handler(metadata=metadata)
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]

        full_content = ""
        tool_call_count = 0

        async for msg, _msg_metadata in agent.astream(
            {"messages": lc_messages},
            config=config,
            stream_mode="messages",
        ):
            if isinstance(msg, ToolMessage):
                result_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                yield {
                    "type": "tool_result",
                    "name": msg.name or "",
                    "content": result_text[:1000],
                }
            elif isinstance(msg, AIMessage):
                if msg.tool_calls:
                    tool_call_count += len(msg.tool_calls)
                    for tc in msg.tool_calls:
                        yield {
                            "type": "tool_call",
                            "name": tc.get("name", ""),
                            "args": tc.get("args", {}),
                        }
                elif msg.content:
                    token = msg.content if isinstance(msg.content, str) else str(msg.content)
                    full_content += token
                    yield {"type": "token", "content": token}

        # Store in conversation memory
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

            # Self-improvement nudge: if this was a complex interaction,
            # store a hint so the agent considers creating a skill next time
            if tool_call_count >= 3:
                user_text = " ".join(m.content for m in messages if m.role == "user")
                self._memory.put(
                    "/knowledge/system/last_complex_task",
                    content=(
                        f"Complex task ({tool_call_count} tool calls): "
                        f"{user_text[:200]}... → Consider creating a skill."
                    ),
                    metadata={"tool_calls": tool_call_count},
                    tags=["nudge", "skill-candidate"],
                )

            await self._memory.maybe_save()

        yield {"type": "done"}
