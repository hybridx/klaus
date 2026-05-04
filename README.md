# klaus

[![CI](https://github.com/<owner>/klaus/actions/workflows/ci.yml/badge.svg)](https://github.com/<owner>/klaus/actions/workflows/ci.yml)

Multi-agent AI assistant platform — standalone or multi-cluster — with local model support and dynamic MCP integration.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          klaus Core                                  │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │  FastAPI      │  │ Task Router  │  │ Event Bus (WebSocket)      │ │
│  │  Gateway      │──│ local-first  │  │ real-time streaming        │ │
│  │  REST + WS    │  │ model select │  │                            │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────────────────────┘ │
│         │                 │                                          │
│  ┌──────┴─────────────────┴──────────────────────────────────────┐  │
│  │                    LangGraph Agent                             │  │
│  │   ReAct loop · memory context · tool execution · tracing      │  │
│  └──────┬──────────────┬──────────────────┬─────────────────────┘  │
│         │              │                  │                          │
│  ┌──────┴──────┐ ┌─────┴──────┐ ┌────────┴────────┐               │
│  │ Model       │ │ Superpower │ │ Memory Tree     │               │
│  │ Registry    │ │ Registry   │ │ /knowledge      │               │
│  │ (LangChain) │ │ (plugins)  │ │ /conversations  │               │
│  │ Ollama, HF, │ │ MCP Bridge │ │ /superpowers    │               │
│  │ vLLM, OAI   │ │ + custom   │ │ SQLite persist  │               │
│  └─────────────┘ └────────────┘ └─────────────────┘               │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  SQLite (memory, conversations, routing rules)             │    │
│  │  MCP Server Manager · Langfuse Observability               │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

For a deep dive comparing klaus to LangGraph, AutoGen, CrewAI, OpenAI Agents SDK, Semantic Kernel, and Google A2A, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — handles venv, deps, and script execution
- [Ollama](https://ollama.ai/) running locally (for the default backend)
- Google Gemini API key (optional — for cloud model fallback, see [Configuration](#api-keys))

### Local development

```bash
git clone <repo-url> && cd klaus
ollama pull llama3.2
uv run klaus-dev
```

`uv` handles the virtual environment and dependencies automatically — no separate install step.

### Common commands

```bash
uv run klaus-dev              # dev server with auto-reload
uv run pytest                 # run tests
uv run ruff check src/ tests/ # lint
uv run ruff check --fix src/  # auto-fix lint issues
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
GOOGLE_API_KEY=AIza...
```

The `.env` file is gitignored — secrets stay local.

### Config file

Edit `config/klaus.yaml` or set environment variables prefixed with `klaus_`:

```yaml
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

log_level: info
```

With `prefer_local: true` (the default), klaus uses Ollama for routine tasks and falls back to Gemini when local models are unavailable or when a task routing rule explicitly targets it.

## Project Structure

```
klaus/
├── config/klaus.yaml            # Default configuration
├── docker-compose.yml           # Podman Compose deployment
├── Containerfile                # Container build
├── pyproject.toml
├── docs/ARCHITECTURE.md         # Architecture deep-dive
├── CONTRIBUTING.md              # Contributor guide
├── .env.example                 # Template for API keys
├── tests/                       # Test suite (107 tests)
└── src/klaus/
    ├── main.py                  # CLI entrypoint
    ├── app.py                   # FastAPI app factory + lifespan
    ├── config/settings.py       # Pydantic settings + YAML loader
    ├── agents/
    │   ├── graph.py             # LangGraph ReAct agent
    │   ├── tools.py             # MCP → LangChain tool bridge
    │   └── tracing.py           # Langfuse integration
    ├── models/
    │   ├── registry.py          # Model backend registry
    │   └── backends/
    │       ├── ollama.py        # Ollama adapter (LangChain)
    │       └── gemini.py        # Google Gemini adapter
    ├── db.py                    # SQLite database (aiosqlite)
    ├── routing/router.py        # Task-based model routing
    ├── memory/
    │   ├── tree.py              # Hierarchical memory tree
    │   ├── store.py             # Persistence (SQLite + JSON fallback)
    │   └── index.py             # Search + context gathering
    ├── superpowers/
    │   ├── base.py              # Superpower abstract class
    │   ├── registry.py          # Superpower lifecycle manager
    │   └── builtin/             # MCP bridge, memory tools
    ├── events/bus.py            # WebSocket event bus
    ├── mcp/manager.py           # Dynamic MCP server manager
    ├── ui/dashboard.html        # Lit web components dashboard
    └── api/
        ├── deps.py              # Shared app state
        └── routes/              # chat, models, mcp, routing,
                                 # events, superpowers, memory,
                                 # conversations
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, code standards, and how to add backends, superpowers, and API routes.

## Roadmap

- [ ] **Agent handoffs** — triage agent delegates to specialist superpowers (inspired by OpenAI Agents SDK)
- [ ] **A2A protocol** — Agent Cards, task state machine, multi-instance discovery (Google A2A)
- [ ] **Guardrails** — input/output validation pipeline
- [ ] **Orchestration patterns** — sequential, concurrent, handoff strategies (Semantic Kernel)
- [ ] **HuggingFace backend** — local transformers inference
- [ ] **vLLM backend** — high-performance model serving
- [ ] **OpenAI-compatible backend** — any provider with an OpenAI-style API
- [ ] **gRPC transport** — cross-language agent protocol for external agent interop
- [ ] **Multi-cluster mode** — NATS/Redis-based message transport between clusters
- [ ] **Code execution sandbox** — safe code execution as a superpower
