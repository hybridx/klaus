# klaus

[![CI](https://github.com/hybridx/klaus/actions/workflows/ci.yml/badge.svg)](https://github.com/hybridx/klaus/actions/workflows/ci.yml)

Multi-agent AI assistant platform — standalone or multi-cluster — with local model support and dynamic MCP integration.

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                             klaus Core                                      │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐        │
│  │  FastAPI      │  │ Task Router  │  │ Event Bus (SSE)            │        │
│  │  Gateway      │──│ local-first  │  │ real-time streaming        │        │
│  │  REST + SSE   │  │ model select │  │                            │        │
│  └──────┬───────┘  └──────┬───────┘  └────────────────────────────┘        │
│         │                 │                                                 │
│  ┌──────┴─────────────────┴──────────────────────────────────────────┐     │
│  │                  Multi-Agent Orchestrator                          │     │
│  │   Planner → Dispatcher → Executors (parallel) → Consolidator      │     │
│  ├────────────────────────────────────────────────────────────────────┤     │
│  │                    LangGraph Agent (single-agent fallback)         │     │
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

For a deep dive comparing klaus to LangGraph, AutoGen, CrewAI, OpenAI Agents SDK, Semantic Kernel, and Google A2A, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — handles venv, deps, and script execution
- [Podman Desktop](https://podman-desktop.io/) — runs PostgreSQL (required) and Ollama containers
- [Ollama](https://ollama.ai/) running locally (for the default backend)
- Google Gemini API key (optional — for cloud model fallback, see [Configuration](#api-keys))

### Local development

```bash
git clone <repo-url> && cd klaus

# Start PostgreSQL (required) — pgvector for embeddings
bash scripts/start-postgres.sh
ollama pull llama3.2

# Build the frontend
cd ui && npm install && npm run build && cd ..

# Start the backend
uv run klaus-dev
```

`uv` handles the Python virtual environment and dependencies automatically — no separate install step.

### Common commands

```bash
# Backend
uv run klaus-dev              # dev server with auto-reload
uv run pytest                 # run tests
uv run ruff check src/ tests/ # lint
uv run ruff check --fix src/  # auto-fix lint issues

# Frontend (from ui/ directory)
npm run dev                   # Vite dev server with HMR (proxies /api → backend)
npm run build                 # production build → src/klaus/ui/dist/
npm run preview               # Preview production build
```

### Podman (containerized)

```bash
podman-compose up -d

# Pull a model into the Ollama container
podman-compose exec ollama ollama pull llama3.2
```

## API

### Chat

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello!"}],
    "model": "llama3.2"
  }'
```

### List Models

```bash
curl http://localhost:8000/api/models
```

### MCP Server Management

Klaus auto-discovers MCP servers from `mcp.json` files (Cursor/Claude format) at:
- `mcp.json` (project root)
- `.cursor/mcp.json` (project)
- `~/.cursor/mcp.json` (global)

Or point to any file explicitly in `config/klaus.yaml`:

```yaml
mcp_config_files:
  - .cursor/mcp.json
  - /path/to/other/mcp.json
```

The `mcp.json` format is the standard Cursor/Claude format:

```json
{
  "mcpServers": {
    "products": { "command": "npx", "args": ["@scarlet-mesh/mcp-products"] },
    "devtools": { "command": "npx", "args": ["chrome-devtools-mcp@latest"] }
  }
}
```

You can also register servers at runtime via API:

```bash
# Register an MCP server at runtime
curl -X POST http://localhost:8000/api/mcp/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "filesystem",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
  }'

# List all MCP servers
curl http://localhost:8000/api/mcp/servers

# List tools from a server
curl http://localhost:8000/api/mcp/servers/filesystem/tools

# Call a tool
curl -X POST http://localhost:8000/api/mcp/servers/filesystem/call \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "list_directory", "arguments": {"path": "/tmp"}}'

# Remove an MCP server
curl -X DELETE http://localhost:8000/api/mcp/servers/filesystem
```

### Conversation History

```bash
# List recent conversation sessions
curl http://localhost:8000/api/conversations/

# Get messages from a specific session
curl http://localhost:8000/api/conversations/my-session-id
```

### Health Check

```bash
curl http://localhost:8000/health
```

## Configuration

### API Keys

Copy `.env.example` to `.env` and add your keys:

```bash
cp .env.example .env
```

```env
DATABASE_URL=postgresql://klaus:klaus@localhost:5432/klaus
GOOGLE_API_KEY=AIza...
HF_TOKEN=hf_...
```

The `.env` file is gitignored — secrets stay local.

### Config file

Edit `config/klaus.yaml` or set environment variables prefixed with `klaus_`:

```yaml
database:
  url: postgresql://klaus:klaus@localhost:5432/klaus

server:
  host: "0.0.0.0"
  port: 8000

default_backend: ollama

model_backends:
  ollama:
    type: ollama
    base_url: http://localhost:11434
    models: [llama3.2]
    default_model: llama3.2
    locality: local

  gemini:
    type: gemini
    base_url: https://generativelanguage.googleapis.com
    default_model: gemini-2.0-flash
    locality: cloud
    # API key loaded from GOOGLE_API_KEY in .env

  huggingface:
    type: huggingface
    default_model: Qwen/Qwen3-235B-A22B
    locality: cloud
    # API key loaded from HF_TOKEN in .env

orchestrator:
  planner_backend: ollama
  planner_model: qwen3:14b
  parallel_execution: true
  md_tools_dir: data/tools

log_level: info
```

With `prefer_local: true` (the default), klaus uses Ollama for routine tasks and falls back to Gemini when local models are unavailable or when a task routing rule explicitly targets it.

The `orchestrator` section enables multi-agent orchestration — complex requests are decomposed by a planner model and dispatched to specialist agents. The planner presents its plan for human approval before execution, and learns from corrections to improve future plans. Define specialist agents as simple Markdown files in `data/agents/`. See [Orchestration Guide](https://hybridx.github.io/klaus/guide/orchestration).

## Project Structure

```
klaus/
├── config/klaus.yaml            # Default configuration
├── docker-compose.yml           # Podman Compose deployment
├── Containerfile                # Container build (Klaus app)
├── Containerfile.postgres       # Container build (PostgreSQL + pgvector)
├── scripts/
│   ├── start-postgres.sh       # Start/build PostgreSQL container
│   └── init-pgvector.sql       # DB init script (enables pgvector)
├── pyproject.toml
├── docs/ARCHITECTURE.md         # Architecture deep-dive
├── CONTRIBUTING.md              # Contributor guide
├── .env.example                 # Template for API keys
├── data/tools/                  # MD-based tool definitions
│   ├── calculator.md
│   ├── date_time.md
│   └── text_transform.md
├── data/agents/                 # MD-based specialist agents
│   ├── code-expert.md
│   ├── creative-writer.md
│   └── analyst.md
├── tests/                       # Test suite (197 tests)
├── ui/                          # Frontend (React + Vite + Tailwind + React Flow)
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx             # React entry point
│       ├── App.tsx              # Root component + page routing
│       ├── index.css            # Tailwind + theme tokens
│       ├── hooks/
│       │   ├── useEventStream.ts # SSE + REST hook
│       │   └── useTheme.ts      # Light/dark theme hook
│       ├── components/
│       │   ├── Layout.tsx       # App shell, header, nav menu
│       │   ├── Sidebar.tsx      # Conversation history sidebar
│       │   └── Markdown.tsx     # Markdown renderer (react-markdown)
│       └── pages/
│           ├── Chat.tsx         # Chat with model selector + image upload
│           ├── Knowledge.tsx    # Knowledge graph visualization
│           ├── Flow.tsx         # Pipeline / orchestrator graph (React Flow)
│           ├── Models.tsx       # Model backend viewer
│           ├── Routing.tsx      # Task routing rules
│           ├── Activity.tsx     # Real-time event log
│           ├── MCP.tsx          # MCP server management
│           └── Superpowers.tsx  # Superpower/tool inspector
└── src/klaus/
    ├── main.py                  # CLI entrypoint
    ├── app.py                   # FastAPI app factory + lifespan
    ├── config/settings.py       # Pydantic settings + YAML loader
    ├── agents/
    │   ├── graph.py             # LangGraph ReAct agent + orchestrate()
    │   ├── orchestrator.py      # Multi-agent orchestrator (planner/dispatcher/executor)
    │   ├── tools.py             # MCP → LangChain tool bridge
    │   └── tracing.py           # Langfuse integration
    ├── models/
    │   ├── registry.py          # Model backend registry
    │   └── backends/
    │       ├── ollama.py        # Ollama adapter (LangChain)
    │       ├── gemini.py        # Google Gemini adapter
    │       └── huggingface.py   # HuggingFace Inference API adapter
    ├── db.py                    # PostgreSQL + pgvector (asyncpg)
    ├── routing/router.py        # Task-based model routing
    ├── memory/
    │   ├── tree.py              # Hierarchical memory tree
    │   ├── store.py             # Persistence (SQLite + JSON fallback)
    │   └── index.py             # Search + context gathering
    ├── superpowers/
    │   ├── base.py              # Superpower abstract class
    │   ├── registry.py          # Superpower lifecycle manager
    │   └── builtin/
    │       ├── mcp_bridge.py    # MCP tool bridge
    │       ├── memory_tools.py  # Memory read/write/search
    │       ├── skills.py        # Self-improving skills system
    │       └── image_gen.py     # Image generation (HF)
    ├── events/bus.py            # SSE event bus
    ├── mcp/
    │   ├── manager.py           # Dynamic MCP server manager
    │   └── md_tools.py          # Markdown-based tool parser
    ├── ui/dist/                 # Built frontend (gitignored)
    └── api/
        ├── deps.py              # Shared app state
        └── routes/              # chat, models, mcp, routing,
                                 # events, superpowers, memory,
                                 # conversations
```

## Documentation

Full documentation is hosted at **[hybridx.github.io/klaus](https://hybridx.github.io/klaus/)** (built with VitePress).

| Guide | What it covers |
|-------|----------------|
| [Getting Started](https://hybridx.github.io/klaus/guide/getting-started) | Setup, prerequisites, dev workflow |
| [Architecture](https://hybridx.github.io/klaus/guide/architecture) | System overview, framework comparisons, change map |
| [Adding Tools](https://hybridx.github.io/klaus/guide/adding-tools) | Creating superpowers and agent tools |
| [Adding Backends](https://hybridx.github.io/klaus/guide/adding-backends) | Adding model backends (Ollama, OpenAI, etc.) |
| [UI Guide](https://hybridx.github.io/klaus/guide/ui-guide) | React frontend architecture, design system |
| [Memory System](https://hybridx.github.io/klaus/guide/memory-system) | Memory tree, pgvector, hybrid search |
| [Orchestration](https://hybridx.github.io/klaus/guide/orchestration) | Multi-agent planner/executor pattern |
| [MD-Based Tools](https://hybridx.github.io/klaus/guide/md-tools) | Creating tools from Markdown files |
| [API Reference](https://hybridx.github.io/klaus/reference/api) | All REST endpoints |
| [SSE Protocol](https://hybridx.github.io/klaus/reference/sse) | Real-time SSE + REST protocol |
| [Configuration](https://hybridx.github.io/klaus/reference/configuration) | YAML + env var reference |
| [Database Schema](https://hybridx.github.io/klaus/reference/database) | PostgreSQL + pgvector schema |

See also [CONTRIBUTING.md](CONTRIBUTING.md) for setup, code standards, and PR process.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, code standards, and how to add backends, superpowers, and API routes.

## Roadmap

- [x] **Multi-agent orchestration** — planner decomposes requests, dispatches to specialist agents, consolidates results
- [x] **MD-based tools** — define agent tools from Markdown files (no code needed)
- [x] **MD-based agents** — define specialist agents from Markdown files (`data/agents/`)
- [x] **Human-in-the-loop** — plan approval: approve, reject, or edit the orchestrator's plan before execution
- [x] **Self-improving plans** — corrections stored in memory, used to improve future plan generation
- [x] **MCP auto-discovery** — auto-load MCP servers from `mcp.json` (Cursor/Claude format)
- [ ] **Agent handoffs** — triage agent delegates to specialist superpowers (inspired by OpenAI Agents SDK)
- [ ] **A2A protocol** — Agent Cards, task state machine, multi-instance discovery (Google A2A)
- [ ] **Guardrails** — input/output validation pipeline
- [x] **HuggingFace backend** — HF Inference API for chat + image generation
- [ ] **vLLM backend** — high-performance model serving
- [ ] **OpenAI-compatible backend** — any provider with an OpenAI-style API
- [ ] **gRPC transport** — cross-language agent protocol for external agent interop
- [ ] **Multi-cluster mode** — NATS/Redis-based message transport between clusters
- [ ] **Code execution sandbox** — safe code execution as a superpower
