# Architecture

klaus is a platform that wraps LangGraph with model routing, persistent memory, a plugin system, and a real-time dashboard.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          klaus Core                                  │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │  FastAPI      │  │ Task Router  │  │ Event Bus (SSE)            │ │
│  │  Gateway      │──│ local-first  │  │ real-time system activity  │ │
│  │  REST + WS    │  │ model select │  │ token + tool streaming     │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────────────────────┘ │
│         │                 │                                          │
│  ┌──────┴─────────────────┴──────────────────────────────────────┐  │
│  │                    LangGraph Agent                             │  │
│  │   ReAct loop · memory context injection · tool execution      │  │
│  │   per-request rebuild with latest tools + routed model        │  │
│  │   tool result streaming · self-improvement reflection         │  │
│  └──────┬──────────────┬──────────────────┬─────────────────────┘  │
│         │              │                  │                          │
│  ┌──────┴──────┐ ┌─────┴──────┐ ┌────────┴────────┐               │
│  │ Model       │ │ Superpower │ │ Memory Tree     │               │
│  │ Registry    │ │ Registry   │ │ /knowledge      │               │
│  │ (LangChain) │ │ (plugins)  │ │ /conversations  │               │
│  │             │ │            │ │ /superpowers     │               │
│  │ ┌─────────┐ │ │ ┌────────┐│ │                  │               │
│  │ │ Ollama  │ │ │ │MCP     ││ │ Hybrid search:   │               │
│  │ │ Gemini  │ │ │ │Bridge  ││ │ keyword + tag +  │               │
│  │ │ HF      │ │ │ │Memory  ││ │ semantic (pgvec) │               │
│  │ │ Custom  │ │ │ │Skills  ││ │ + recency boost  │               │
│  │ └─────────┘ │ │ │ImgGen  ││ │                  │               │
│  └─────────────┘ │ │Custom  ││ │ PostgreSQL +     │               │
│                  │ └────────┘│ │ pgvector          │               │
│                  └───────────┘ └──────────────────┘               │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                    MCP Server Manager                      │    │
│  │    dynamic registration · tool discovery · runtime calls   │    │
│  └────────────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                    Observability (Langfuse)                 │    │
│  │    trace every LLM call · tool usage · latency · cost      │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### Local-first model routing

The task router prefers local models (Ollama) and falls back to cloud (Gemini, HuggingFace). You can route coding tasks to CodeLlama, creative to GPT-4, analysis to Qwen — all from a single config file.

### Memory tree, not just vector store

Instead of flat vector embeddings, klaus uses a hierarchical tree where related knowledge clusters naturally. Paths like `/knowledge/python/tips` are human-readable and debuggable. **Both** keyword and semantic (pgvector) search are used in a [hybrid search](/guide/memory-system).

### Superpowers as the extension model

Every capability is a [Superpower](/guide/adding-tools) — MCP bridges, memory tools, image generation, self-improving skills. Each one gets its own memory branch, lifecycle hooks, and LangChain tools.

### Per-request agent rebuild

The LangGraph agent is rebuilt on every request with:
- The **routed model** (based on task type and routing rules)
- The **latest tools** from all active superpowers
- **Memory context** gathered via hybrid search

This means you can register a new superpower at runtime and it's immediately available.

## Change Map

Use this table when you need to find the right files for a change:

| I want to... | Files to change |
|--------------|----------------|
| Add a model backend | `models/backends/new.py`, `models/registry.py`, `config/klaus.yaml` |
| Add a superpower/tool | `superpowers/builtin/new.py`, `app.py` |
| Add an API endpoint | `api/routes/new.py`, `app.py` |
| Add a UI page | `ui/src/pages/New.tsx`, `App.tsx`, `Layout.tsx` |
| Change memory structure | `memory/tree.py`, `memory/store.py`, `memory/index.py` |
| Change database schema | `db.py` |
| Change agent behavior | `agents/graph.py` |
| Change task routing | `routing/router.py`, `config/klaus.yaml` |
| Add an SSE event | `events/bus.py`, `api/routes/events.py`, `ui/src/pages/Chat.tsx` |
| Add a container service | `docker-compose.yml`, new `Containerfile.*`, `scripts/` |

## Framework Comparisons

klaus draws inspiration from several AI agent frameworks while taking a different approach:

| Concept | AutoGen | CrewAI | OpenAI Agents | klaus |
|---------|---------|--------|---------------|-------|
| Agent runtime | Event-driven actors | Role-based crews | Agent + Handoff | ReAct via LangGraph |
| Multi-agent | Group chat | Crew assigns tasks | Handoffs | Single agent (multi planned) |
| Memory | Teachable agents | Vector + entity | Thread history | Hierarchical tree + pgvector |
| Tools | Function decorators | `@tool` decorator | `@function_tool` | Superpowers + MCP bridge |
| Model support | LiteLLM | Any via LiteLLM | OpenAI only | Registry (Ollama, HF, Gemini, ...) |

For a detailed comparison, see the full [ARCHITECTURE.md](https://github.com/hybridx/klaus/blob/main/docs/ARCHITECTURE.md) on GitHub.
