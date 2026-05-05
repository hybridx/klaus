# klaus Architecture

This document explains klaus's architecture by comparing it to the major AI agent frameworks. If you're coming from AutoGen, CrewAI, OpenAI Agents SDK, or Semantic Kernel, this maps familiar concepts to how klaus works — and where it diverges.

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                             klaus Core                                     │
│                                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐        │
│  │  FastAPI      │  │ Task Router  │  │ Event Bus (SSE)            │       │
│  │  Gateway      │──│ local-first  │  │ real-time streaming        │       │
│  │  REST + SSE   │  │ model select │  │ token + tool + phase       │       │
│  └──────┬───────┘  └──────┬───────┘  └────────────────────────────┘        │
│         │                 │                                                │
│  ┌──────┴─────────────────┴──────────────────────────────────────────┐     │
│  │                  Multi-Agent Orchestrator                          │    │
│  │   Planner → Human Approval → Dispatch → ReAct Executors           │     │
│  │   Sense → Plan → Act → Reflect (per step)                         │     │
│  ├────────────────────────────────────────────────────────────────────┤    │
│  │                    LangGraph Agent (single-agent fallback)         │    │
│  │   ReAct loop · memory context · tool execution · tracing          │     │
│  └──────┬──────────────┬──────────────────┬──────────────────────┘     │
│         │              │                  │                              │
│  ┌──────┴──────┐ ┌─────┴──────┐ ┌────────┴────────┐                   │
│  │ Model       │ │ Superpower │ │ Memory Tree     │                   │
│  │ Registry    │ │ Registry   │ │ /knowledge      │                   │
│  │ (LangChain) │ │ (plugins)  │ │ /conversations  │                   │
│  │ Ollama, HF, │ │ MCP Bridge │ │ /superpowers    │                   │
│  │ Gemini      │ │ + MD tools │ │ pgvector embeds │                   │
│  └─────────────┘ └────────────┘ └─────────────────┘                   │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  PostgreSQL + pgvector (memory, conversations, embeddings)     │    │
│  │  MCP Server Manager · MD-Based Tools · Langfuse Observability  │    │
│  └────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────────────┘
```

## ReAct (Reason + Act) Loop

Every execution path in klaus — whether single-agent or multi-agent orchestrator — follows the **Sense → Plan → Act → Reflect** cycle:

```
┌────────────────────────────────────────────────────────────┐
│                      ReAct Loop                             │
│                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐ │
│  │  SENSE  │───▶│  PLAN   │───▶│   ACT   │───▶│ REFLECT │ │
│  │         │    │         │    │         │    │         │ │
│  │ Retrieve│    │ Reason  │    │ Execute │    │Validate │ │
│  │ context │    │ & break │    │ tools + │    │ output  │ │
│  │ from    │    │ into    │    │ LLM     │    │ & loop  │ │
│  │ memory  │    │ steps   │    │ calls   │    │ if fail │ │
│  └─────────┘    └─────────┘    └─────────┘    └────┬────┘ │
│       ▲                                            │       │
│       └────────────────────────────────────────────┘       │
│                     (retry on failure)                       │
└────────────────────────────────────────────────────────────┘
```

| Phase | What it does | Implementation |
|-------|-------------|----------------|
| **Sense** | Gathers context — user request, memory, prior step results, relevant knowledge | `_build_step_context()` in orchestrator, `_build_memory_context()` in agent |
| **Plan** | The LLM reasons about how to approach the task, exposed as thinking/reasoning blocks in the UI | LLM `reasoning_content` streamed as `thinking` SSE events |
| **Act** | Execute the task using tools (MCP, memory, superpowers) and LLM generation | LangGraph `create_react_agent` with tool harness |
| **Reflect** | Evaluate the result — check for errors, assess quality, decide if retry is needed | `_reflect()` method compares output against acceptance criteria |

The reflect phase can trigger a retry (up to 2 retries per step), feeding the failure context back into the sense phase.

## UI Architecture

Klaus uses a **two-layout system**:

```
┌─────────────────────────────────────────────────────────────┐
│  Chat Layout                                                 │
│  ┌──────────┐ ┌────────────────────────────────────────────┐│
│  │ Sidebar  │ │  Header: Klaus  [Docs] [●] [☀] [⚙]       ││
│  │          │ │  ┌──────────────────────────────────────┐  ││
│  │ Sessions │ │  │  Chat / Flow / Knowledge content     │  ││
│  │          │ │  │                                      │  ││
│  │          │ │  │  To-dos widget · Task queue          │  ││
│  │          │ │  │  Thinking blocks · Phase indicators  │  ││
│  │          │ │  │  Orchestrator plan visualization     │  ││
│  └──────────┘ │  └──────────────────────────────────────┘  ││
│               └────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Settings Layout  (gear icon from chat header)              │
│  ┌──────────────┐ ┌────────────────────────────────────────┐│
│  │ ← Back to    │ │  Page Title                            ││
│  │   Chat       │ │  ┌──────────────────────────────────┐  ││
│  │              │ │  │                                  │  ││
│  │ SETTINGS     │ │  │  Page content                    │  ││
│  │  Models      │ │  │  (Models, Routing, MCP, etc.)    │  ││
│  │  Routing     │ │  │                                  │  ││
│  │  MCP Servers │ │  │                                  │  ││
│  │  Superpowers │ │  └──────────────────────────────────┘  ││
│  │              │ └────────────────────────────────────────┘│
│  │ OBSERVABILITY│                                           │
│  │  Pipeline    │                                           │
│  │  Activity    │                                           │
│  │  Knowledge   │                                           │
│  │              │                                           │
│  │ [Docs] [●◉]  │                                           │
│  └──────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

The settings panel uses a persistent sidebar with grouped navigation (inspired by Cursor/VS Code settings). The chat page keeps a compact header with a gear icon to enter settings.

## Extension Model

Klaus is designed to be extended by developers at multiple levels:

| Extension point | Complexity | Description |
|----------------|-----------|-------------|
| **MCP server** | JSON config | The **preferred** way to add capabilities — external tool servers from `mcp.json` |
| **MCP server (OAuth)** | Just a URL | OAuth2 servers (Atlassian, GitHub) — SDK handles auth automatically |
| **MD agent** (`data/agents/*.md`) | Drop a file | Specialist agent that uses MCP tools, with preferred model |
| **MD tool** (`data/tools/*.md`) | Drop a file | Standalone tool with Python implementation |
| **Superpower class** | Python class | Only for capabilities that don't have an MCP server (memory, skills) |
| **Model backend** | Python class | New LLM provider (Ollama, Gemini, OpenAI, vLLM, etc.) |
| **UI page** | React component | New page in the settings panel or chat area |

### MCP-First Philosophy

**Don't build custom superpowers for things MCP servers already do.** The MCP ecosystem has servers for Jira, GitHub, GitLab, Slack, databases, file systems, and hundreds more. Klaus agents access all of these through the MCP Bridge — no custom code needed.

```
┌──────────────┐      ┌───────────────┐      ┌──────────────────┐
│ Super Agent   │─────▶│ Specialist    │─────▶│ MCP Servers      │
│ (Planner)     │      │ Agents        │      │                  │
│               │      │               │      │ ● Atlassian      │
│ Creates plan  │      │ ● CVE Agent   │      │ ● GitHub         │
│ Human approval│      │ ● Docs Agent  │      │ ● Filesystem     │
│ Dispatches    │      │ ● Dev Agent   │      │ ● Chrome DevTools│
└──────────────┘      └───────────────┘      │ ● Products       │
                                              │ ● Any MCP server │
                                              └──────────────────┘
```

The workflow:
1. **Super Agent** receives a complex request and creates a plan
2. Human reviews and approves/edits the plan
3. **Specialist agents** execute each step using their preferred models
4. Agents call **MCP tools** when they need external data or actions (Jira tickets, GitHub PRs, etc.)
5. Results flow back to the Super Agent for consolidation

Only build a custom superpower when there's no MCP server for the capability (e.g., the memory system, self-improving skills).

See the [Developer Extension Guide](./guide/extending-klaus.md) for walkthroughs with example prompts.

## MCP OAuth2 Flow

OAuth is handled entirely by the MCP Python SDK's built-in `OAuthClientProvider` — no manual configuration is needed. Just provide the server URL and click Connect:

```
┌─────────┐      ┌──────────┐       ┌──────────┐      ┌──────────┐
│ Klaus UI │      │ MCP SDK  │       │ Browser  │      │  OAuth   │
│          │      │ (httpx)  │       │  Tab     │      │ Provider │
└────┬─────┘      └────┬─────┘       └────┬─────┘      └────┬─────┘
     │ Click Connect   │                   │                  │
     │────────────────▶│                   │                  │
     │                 │ POST /v1/mcp →401 │                  │
     │                 │───────────────────────────────────▶ │
     │                 │                   │                  │
     │                 │ Discover PRM +    │                  │
     │                 │ OAuth metadata    │                  │
     │                 │───────────────────────────────────▶ │
     │                 │                   │                  │
     │                 │ Dynamic client    │                  │
     │                 │ registration      │                  │
     │                 │───────────────────────────────────▶ │
     │                 │                   │                  │
     │                 │ PKCE challenge    │                  │
     │ {auth_url}      │                   │                  │
     │◀────────────────│                   │                  │
     │ window.open()   │                   │                  │
     │────────────────────────────────────▶│  User consents   │
     │                 │                   │─────────────────▶│
     │                 │                   │                  │
     │                 │ GET /callback?code=X&state=Y         │
     │                 │◀─────────────────────────────────── │
     │                 │                   │                  │
     │                 │ Exchange code     │                  │
     │                 │ for token (auto)  │                  │
     │                 │───────────────────────────────────▶ │
     │                 │                   │                  │
     │                 │ Retry with token  │                  │
     │                 │───────────────────────────────────▶ │
     │                 │                   │                  │
     │ Poll → connected│                   │                  │
     │◀────────────────│                   │                  │
     ▼                 ▼                   ▼                  ▼
```

This is the same mechanism Cursor uses. No `client_id`, `token_url`, or any OAuth config is needed in `mcp.json` — the SDK discovers everything from the server's well-known endpoints.

### Connection Robustness

Klaus's MCP manager includes several resilience features that match Cursor's behaviour:

| Feature | Purpose |
|---------|---------|
| **`LenientReadStream`** | Wraps the stdio read stream to silently drop non-JSON parse errors. Some MCP servers write banners (e.g. "Server running on stdio") to stdout before JSON-RPC begins — Cursor's TypeScript client ignores these, and this wrapper does the same for the Python SDK. |
| **Async context manager session** | `ClientSession` is entered via `async with` so its internal `_receive_loop` is started before `initialize()` — required by the MCP Python SDK. |
| **Extended stdio timeout (45 s)** | `npx`-based servers can take 10+ seconds for initial package download. Stdio servers get a 45-second startup window vs 15 seconds for HTTP. |
| **Cleanup noise suppression** | `BrokenResourceError` / `ClosedResourceError` during task cancellation are expected artefacts, not real errors — they're logged at debug level instead of polluting the error log. |
| **Streamable HTTP → SSE fallback** | URL-based servers first try the new Streamable HTTP transport; if it fails, fall back to SSE. |

## Comparison with Other Agent Frameworks

### LangGraph

**What it is:** Directed graph-based agent orchestration from LangChain. Agents are state machines where nodes are processing steps and edges define transitions.

**How klaus relates:** klaus *uses* LangGraph as its agent runtime. The `klausAgent` class builds a `create_react_agent` per request, feeding it the routed LLM and tools collected from the superpower registry. LangGraph handles the ReAct loop, tool calling, and message management.

| Concept | LangGraph | klaus |
|---|---|---|
| Agent definition | Graph nodes + edges | `klausAgent` wraps `create_react_agent` |
| State management | Explicit `StateGraph` with checkpointing | Memory tree + per-request rebuild |
| Tool binding | Pass to `create_react_agent` | Superpowers collect tools automatically |
| Model selection | Caller chooses LLM | Task router selects model based on rules + locality |
| Observability | LangSmith | Langfuse (or any LangChain callback) |

**Key difference:** LangGraph is a library — you build your own agent loop. klaus is a platform that wraps LangGraph with model routing, memory, plugin management, MCP, and a real-time UI.

---

### AutoGen (Microsoft)

**What it is:** Event-driven, multi-agent conversation framework. Agents are actors that exchange messages asynchronously. v0.4 has three layers: Core (actor framework), AgentChat (high-level API), Extensions.

**Architecture comparison:**

| Concept | AutoGen | klaus |
|---|---|---|
| Agent runtime | Event-driven actor model with `@event`, `@rpc` decorators | Request-driven ReAct agent, event bus for side-channel |
| Multi-agent | Group chat, nested conversations, agent-to-agent messaging | Orchestrator with planner → specialist agents |
| Memory | Teachable agents with local storage | Hierarchical tree with path-based access |
| Tool use | Function decorators, code execution sandbox | MCP bridge + superpower tools |
| Model support | OpenAI, Anthropic, local via LiteLLM | Model registry with local-first routing |
| Deployment | Python process, distributed via gRPC | Podman containers, FastAPI gateway |

**What klaus can learn from AutoGen:**
- **Event-driven messaging between agents** — AutoGen's actor model where agents react to messages asynchronously is cleaner than request-response for multi-agent scenarios. klaus's event bus already broadcasts events; extending it to agent-to-agent messaging is a natural next step.
- **Conversation patterns** — AutoGen's group chat, two-agent chat, and nested chat patterns are well-tested orchestration models. klaus should adopt similar patterns when adding multi-agent support.
- **Code execution sandbox** — AutoGen provides safe code execution in Docker containers. klaus could add this as a superpower.

---

### CrewAI

**What it is:** Role-based multi-agent framework. You define "crews" of agents, each with a role, goal, and backstory. Tasks are assigned to specific agents and executed sequentially or in parallel.

**Architecture comparison:**

| Concept | CrewAI | klaus |
|---|---|---|
| Agent identity | Role + goal + backstory strings | MD-based agents with capabilities + system prompt |
| Orchestration | Crew assigns tasks to role-specialized agents | Planner → human approval → specialist agents |
| Memory | Short-term (conversation), long-term (vector), entity memory | Tree-structured memory with keyword + semantic search |
| Tools | `@tool` decorator, built-in web search/file ops | MCP tools + superpower tools + MD tools |
| Delegation | Agent A can delegate to Agent B | Orchestrator dispatches to specialist agents |

**What klaus can learn from CrewAI:**
- **Role specialization** — Instead of one agent with all tools, create specialist agents (coding agent, research agent, writing agent) that the main agent can delegate to. Each specialist could be a superpower.
- **Task decomposition** — CrewAI's "process" concept (sequential, hierarchical) for breaking complex tasks into steps that different agents handle. klaus's task router already assigns models per task type; extending this to assign whole agents per task type is logical.
- **Structured output** — CrewAI enforces Pydantic models for task output. klaus should support structured output validation.

---

### OpenAI Agents SDK

**What it is:** OpenAI's production framework built on three primitives: Agents (LLM + instructions + tools), Handoffs (transfer to specialist agent), and Guardrails (input/output validation).

**Architecture comparison:**

| Concept | OpenAI Agents SDK | klaus |
|---|---|---|
| Agent definition | `Agent(name, instructions, tools, handoffs)` | `klausAgent` with memory context + superpower tools |
| Tool use | `@function_tool` decorator with auto-schema | MCP tools auto-bridged to LangChain tools |
| Handoffs | Agent transfers control to specialist | Orchestrator dispatches to specialist agents |
| Guardrails | Input/output validation with custom logic | Not yet |
| Model | OpenAI models only | Any model via registry (Ollama, HF, OpenAI, etc.) |
| Memory | Conversation history in thread | Tree-structured persistent memory |

**What klaus can learn from OpenAI Agents SDK:**
- **Handoffs** — The cleanest multi-agent pattern. A triage agent decides which specialist handles the request and transfers control. In klaus, each superpower could become a specialist agent that the main agent hands off to.
- **Guardrails** — Input validation (check if the request is appropriate) and output validation (check if the response meets quality standards). This should be a built-in system, not a superpower.
- **Simplicity** — Three primitives (Agent, Handoff, Guardrail) cover most use cases. klaus should avoid over-engineering orchestration.

---

### Semantic Kernel (Microsoft)

**What it is:** Microsoft's AI orchestration SDK. Agents are built on a Kernel (plugin host) with five orchestration patterns: Sequential, Concurrent, Handoff, Group Chat, and Magentic.

**Architecture comparison:**

| Concept | Semantic Kernel | klaus |
|---|---|---|
| Plugin system | Kernel plugins with functions | Superpowers with LangChain tools |
| Orchestration | 5 patterns (sequential, concurrent, handoff, group, magentic) | Planner + specialist agents with human approval |
| State | AgentThread abstraction | Memory tree |
| Languages | C#, Python, Java | Python |

**What klaus can learn from Semantic Kernel:**
- **Orchestration patterns as first-class** — Having a unified interface for sequential, concurrent, and handoff patterns that you can switch between without rewriting agent logic. klaus could implement these as different "strategy" options in the task router.
- **Agent Thread abstraction** — Clean separation between agent logic and conversation state management.

---

### Google A2A Protocol

**What it is:** An open protocol for agent-to-agent communication. Not a framework — a standard. Agents publish "Agent Cards" describing their capabilities, communicate via JSON-RPC 2.0 over HTTP, and manage tasks through state machines.

**How it relates to klaus:**

| Concept | A2A | klaus equivalent |
|---|---|---|
| Agent discovery | Agent Cards at `/.well-known/agent.json` | Not yet — klaus agents don't self-describe |
| Communication | JSON-RPC 2.0 over HTTP(S) | FastAPI REST + SSE |
| Task lifecycle | submitted → working → completed | Chat request → response |
| Complementary to | MCP (agent-to-tool) | Already uses MCP for tools |

**What klaus should adopt from A2A:**
- **Agent Cards** — Each klaus instance should publish a `/.well-known/agent.json` describing its capabilities, superpowers, and available models. This enables discovery in multi-cluster setups.
- **Task state machine** — Formalize task lifecycle beyond simple request/response. Long-running tasks should have states (submitted, working, completed, failed) with webhook notifications.
- **Multi-cluster communication** — A2A over HTTP is the natural protocol for connecting multiple klaus instances. Each instance is an A2A server, and they discover each other via Agent Cards.

## Where klaus is Different

Most frameworks force a choice: you either use their models, their tools, or their orchestration. klaus is designed differently:

1. **Local-first model routing** — No other framework has a task router that prefers local models and falls back to cloud. AutoGen and CrewAI assume you pick one provider. klaus lets you run coding tasks on a local CodeLlama while routing creative tasks to GPT-4.

2. **Memory tree, not vector store** — Every framework defaults to vector embeddings for memory. klaus uses a hierarchical tree where related knowledge clusters naturally. This makes retrieval predictable and debuggable — you can `ls /knowledge/user` instead of hoping cosine similarity returns the right thing.

3. **Superpowers as the extension model** — Instead of "just add another agent" (CrewAI, AutoGen) or "just add another tool" (OpenAI), klaus superpowers are a hybrid: they bundle tools, memory, and lifecycle into a single unit. An MCP server connection becomes a superpower. A code analysis engine becomes a superpower. Each one gets its own branch in the memory tree.

4. **MCP as the tool standard** — While other frameworks define custom tool interfaces, klaus uses Model Context Protocol for external tool integration, making it compatible with the growing MCP ecosystem.

5. **Human-in-the-loop orchestration** — The planner pauses for human approval before executing. Corrections are stored and improve future plans. No other framework has this feedback loop built in.

6. **MD-based extensibility** — Drop a Markdown file to add a tool or agent. No code changes, no restarts of the core (restart required but no code edits). This lowers the barrier for non-Python developers to contribute.

## Planned Architecture Additions

Based on the analysis above, these are the architectural additions planned for klaus, roughly in priority order:

| Feature | Inspired by | Status |
|---|---|---|
| MCP OAuth2 flow | Cursor | **Done** — SDK-based PKCE flow, zero config (same as Cursor) |
| Config-driven MCP | Cursor/Claude | **Done** — servers from `mcp.json`, OAuth auto-discovered |
| MCP-first agents | — | **Done** — agents use MCP servers, no custom integrations needed |
| Agent handoffs | OpenAI Agents SDK | Planned — triage agent delegates to specialist superpowers |
| A2A protocol | Google A2A | Planned — Agent Cards, task state machine, multi-instance discovery |
| Guardrails | OpenAI Agents SDK | Planned — input/output validation pipeline |
| Orchestration patterns | Semantic Kernel | Planned — sequential, concurrent, handoff strategies |
| Agent-to-agent messaging | AutoGen | Planned — event-driven communication between agents |
| Code execution sandbox | AutoGen | Planned — safe code execution as a superpower |
| Structured output | CrewAI | Planned — Pydantic model validation on agent responses |
| gRPC transport | — | Planned — cross-language agent protocol for external agents |

## Change Map — What to Touch Where

Use this table to find the right files when making changes:

| I want to... | Files to change |
|--------------|----------------|
| **Add a model backend** | `models/backends/new.py`, `models/registry.py` (factory), `config/klaus.yaml`, `pyproject.toml` |
| **Add a superpower/tool** | `superpowers/builtin/new.py`, `app.py` (register), `tests/` |
| **Add an MD tool** | `data/tools/your_tool.md` (no code changes) |
| **Add an MD agent** | `data/agents/your_agent.md` (no code changes) |
| **Add an API endpoint** | `api/routes/new.py`, `app.py` (mount router) |
| **Add a UI page** | `ui/src/pages/New.tsx`, `ui/src/App.tsx` (type + render), `ui/src/components/Layout.tsx` (nav) |
| **Change the memory tree structure** | `memory/tree.py`, possibly `memory/store.py` and `memory/index.py` |
| **Change the database schema** | `db.py` (`_SCHEMA`), migration logic in `connect()` |
| **Change the agent behavior** | `agents/graph.py` (`_SYSTEM_PROMPT`, `stream()`, `_build_memory_context`) |
| **Change task routing** | `routing/router.py`, `config/klaus.yaml` (`task_routing` section) |
| **Change the event bus** | `events/bus.py` (add `EventType`), `api/routes/events.py` (forward events) |
| **Change config structure** | `config/settings.py` (Pydantic models), `config/klaus.yaml`, `app.py` (usage) |
| **Add a new SSE event** | `events/bus.py` (EventType), `api/routes/events.py`, `ui/src/pages/Chat.tsx` (handler) |
| **Add a container service** | `docker-compose.yml`, new `Containerfile.*`, `scripts/` |

## Documentation

Detailed guides for each area:

| Doc | What it covers |
|-----|----------------|
| [ADDING_TOOLS.md](./ADDING_TOOLS.md) | Creating superpowers and tools, the plugin system |
| [ADDING_AGENTS.md](./ADDING_AGENTS.md) | Adding model backends, the registry, vision support |
| [UI_GUIDE.md](./UI_GUIDE.md) | React frontend architecture, design system, adding pages |
| [API_REFERENCE.md](./API_REFERENCE.md) | All REST and SSE endpoints |
| [MEMORY_SYSTEM.md](./MEMORY_SYSTEM.md) | Memory tree, pgvector embeddings, hybrid search |
| [Extending klaus](./guide/extending-klaus.md) | Developer extension guide with example prompts |
