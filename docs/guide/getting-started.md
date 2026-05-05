# Getting Started

This guide walks you through setting up klaus for local development.

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Backend runtime |
| [uv](https://docs.astral.sh/uv/) | Latest | Fast Python package manager |
| Node.js | 18+ | Frontend build toolchain |
| [Podman Desktop](https://podman-desktop.io/) | Latest | Container runtime (PostgreSQL) |
| [Ollama](https://ollama.ai/) | Latest | Local model serving (optional) |

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/hybridx/klaus.git
cd klaus
```

### 2. Start PostgreSQL

klaus uses PostgreSQL with pgvector for persistence and vector embeddings. A helper script handles everything:

```bash
bash scripts/start-postgres.sh
```

This will:
- Build the `klaus-postgres` image (PostgreSQL 17 + pgvector) if needed
- Create and start the container
- Wait for the database to be ready
- Print the connection URL

::: tip
The default connection URL is `postgresql://klaus:klaus@localhost:5432/klaus`. Override it via `DATABASE_URL` in `.env` or `database.url` in `config/klaus.yaml`.
:::

### 3. Build the frontend

```bash
cd ui
npm install
npm run build
cd ..
```

### 4. Start the development server

```bash
uv run klaus-dev
```

`uv` creates the virtual environment and installs all Python dependencies automatically on first run.

Open [http://localhost:8000](http://localhost:8000) — you should see the klaus dashboard.

## Development Workflow

For the best experience, run the backend and frontend dev servers simultaneously:

::: code-group

```bash [Terminal 1 — Backend]
uv run klaus-dev
# Runs on http://localhost:8000 with auto-reload
```

```bash [Terminal 2 — Frontend]
cd ui && npm run dev
# Runs on http://localhost:5173 with HMR
# Proxies /api/* to the backend
```

:::

### Common Commands

```bash
# Linting
uv run --extra dev ruff check src/ tests/
uv run --extra dev ruff check --fix src/

# Testing
uv run --extra dev pytest tests/ -v

# Frontend build
cd ui && npm run build

# Container management
bash scripts/start-postgres.sh     # start PostgreSQL
podman-compose up -d               # start all services
podman-compose down                # stop all services
```

## Project Structure

```
klaus/
├── config/
│   └── klaus.yaml              # Main configuration
├── docs/                       # This documentation site (VitePress)
├── scripts/
│   ├── start-postgres.sh       # PostgreSQL container management
│   └── init-pgvector.sql       # pgvector extension init
├── src/klaus/                  # Python backend
│   ├── agents/                 # LangGraph agent, tool bridges, tracing
│   ├── api/                    # FastAPI routes
│   │   └── routes/             # Endpoint modules
│   ├── config/                 # Pydantic settings, YAML loader
│   ├── events/                 # SSE event bus
│   ├── mcp/                    # MCP server manager
│   ├── memory/                 # Memory tree, index, store
│   ├── models/                 # Model registry + backends
│   │   └── backends/           # Ollama, Gemini, HuggingFace
│   ├── routing/                # Task-based model routing
│   ├── superpowers/            # Plugin system
│   │   └── builtin/            # MCP bridge, memory, skills, image gen
│   └── ui/dist/                # Built frontend (gitignored)
├── tests/                      # pytest test suite
├── ui/                         # React frontend
│   ├── src/
│   │   ├── components/         # Layout, Sidebar, Markdown
│   │   ├── hooks/              # useEventStream, useTheme
│   │   └── pages/              # Chat, Knowledge, Flow, Models, ...
│   ├── vite.config.ts
│   └── package.json
├── Containerfile               # App container image
├── Containerfile.postgres      # PostgreSQL + pgvector image
├── docker-compose.yml          # Full stack compose (use with podman-compose)
└── pyproject.toml              # Python dependencies
```

## Configuration

The main config file is `config/klaus.yaml`. Environment variables can also be used:

::: code-group

```yaml [config/klaus.yaml]
server:
  host: "0.0.0.0"
  port: 8000

model_backends:
  ollama:
    type: ollama
    base_url: http://localhost:11434
    default_model: llama3.2
    locality: local

database:
  url: postgresql://klaus:klaus@localhost:5432/klaus
  pool_min: 2
  pool_max: 10

task_routing:
  coding:
    preferred_backend: ollama
    preferred_model: granite-code:8b
  chat:
    preferred_backend: ollama
    preferred_model: llama3.2
```

```bash [.env]
DATABASE_URL=postgresql://klaus:klaus@localhost:5432/klaus
GOOGLE_API_KEY=your-key-here
HF_TOKEN=hf_your-token-here
```

:::

## What's Next?

- [Architecture Overview](/guide/architecture) — understand how the pieces fit together
- [Adding Tools](/guide/adding-tools) — create your first superpower
- [Adding Model Backends](/guide/adding-backends) — connect a new LLM provider
- [UI Guide](/guide/ui-guide) — contribute to the React frontend
