# Contributing to klaus

Thanks for your interest in contributing. This guide covers everything you need to get started.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)
- Node.js 18+ and npm (for the frontend)
- [Podman Desktop](https://podman-desktop.io/) (required — runs PostgreSQL with pgvector)
- [Ollama](https://ollama.ai/) (for local model testing, optional)

## Setup

```bash
git clone <repo-url> && cd klaus

# Start PostgreSQL (required for persistence + vector embeddings)
bash scripts/start-postgres.sh

# Build the frontend
cd ui && npm install && npm run build && cd ..

# Start the backend
uv run klaus-dev
```

`uv` creates the Python virtual environment and installs all dependencies automatically on first run.

PostgreSQL with pgvector is required. The default connection URL (`postgresql://klaus:klaus@localhost:5432/klaus`) works out of the box with the provided `docker-compose.yml` (run via `podman-compose`). Override it via `DATABASE_URL` in `.env` or `database.url` in `config/klaus.yaml`.

## Development

### Backend

```bash
uv run klaus-dev              # start dev server with auto-reload
uv run ruff check src/ tests/ # run ruff linter
uv run ruff check --fix src/  # auto-fix lint issues
uv run pytest                 # run test suite
```

The backend runs at `http://localhost:8000/` with debug logging and hot reload on Python changes.

### Frontend

```bash
cd ui
npm run dev                   # Vite dev server at http://localhost:5173
npm run build                 # production build → src/klaus/ui/dist/
npm run preview               # preview production build locally
```

The Vite dev server proxies `/api/*` requests to the backend at `localhost:8000`, so you get hot module replacement for frontend changes while the API stays live. Run both simultaneously for the best experience.

## Project Layout

```
ui/                  Frontend (React + Vite + Tailwind CSS + React Flow)
├── src/
│   ├── main.tsx         React entry point
│   ├── App.tsx          Root component + page state
│   ├── index.css        Tailwind imports + theme tokens
│   ├── hooks/           React hooks (useEventStream, useTheme)
│   ├── components/      Shared components (Layout, Sidebar, Markdown)
│   └── pages/           Page components (Chat, Knowledge, Flow, Models, Routing, Activity)
├── index.html
├── vite.config.ts
└── tsconfig.json

src/klaus/           Backend (Python + FastAPI)
├── agents/          LangGraph agent, tool bridges, Langfuse tracing
├── api/             FastAPI routes (chat, models, mcp, routing, memory, superpowers)
├── config/          Pydantic settings, YAML loader
├── events/          SSE event bus
├── mcp/             Dynamic MCP server manager
├── memory/          Tree-structured persistent memory
├── models/          Model registry + LangChain backends (Ollama, Gemini, HuggingFace)
├── routing/         Task-based model routing (local-first)
├── superpowers/     Plugin system (MCP bridge, memory, skills, image gen)
└── ui/dist/         Built frontend output (gitignored)
```

## How to Contribute

We have detailed guides for each area of the codebase. Start with the relevant guide:

| Guide | For |
|-------|-----|
| **[docs/ADDING_TOOLS.md](docs/ADDING_TOOLS.md)** | Creating superpowers and agent tools |
| **[docs/ADDING_AGENTS.md](docs/ADDING_AGENTS.md)** | Adding model backends (Ollama, OpenAI, etc.) |
| **[docs/UI_GUIDE.md](docs/UI_GUIDE.md)** | Working on the React frontend |
| **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)** | All REST and SSE endpoints |
| **[docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md)** | Memory tree, embeddings, pgvector |
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | System overview and framework comparison |

### Quick Summary

**Adding a model backend:** Create `src/klaus/models/backends/your_backend.py`, register in `registry.py`, add config in `klaus.yaml`. See [ADDING_AGENTS.md](docs/ADDING_AGENTS.md).

**Adding a superpower/tool:** Create `src/klaus/superpowers/builtin/your_power.py`, register in `app.py`. See [ADDING_TOOLS.md](docs/ADDING_TOOLS.md).

**Adding an API endpoint:** Create `src/klaus/api/routes/your_route.py`, mount in `app.py`. See [API_REFERENCE.md](docs/API_REFERENCE.md).

**Adding a UI page:** Create `ui/src/pages/YourPage.tsx`, add to `App.tsx` and `Layout.tsx`. See [UI_GUIDE.md](docs/UI_GUIDE.md).

**Modifying memory/search:** See [MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md) for the tree, embeddings, and hybrid search architecture.

## Code Standards

### Style

- Python 3.12+ features are encouraged (type unions with `|`, `StrEnum`, etc.)
- Run `uv run ruff check src/ tests/` before committing — CI will fail on lint errors
- Line length limit: 100 characters
- Ruff rules: `E, F, I, N, UP, B, SIM, RUF`

### Commits

- Write concise commit messages focused on the "why"
- Keep commits focused — one logical change per commit
- PRs should be reasonably sized and self-contained

### Testing

- Write tests for new modules in the `tests/` directory
- Use `pytest` with `pytest-asyncio` for async tests
- Tests must pass without Ollama or any external service running (mock backends)
- Run `uv run pytest` to verify locally before pushing

### Documentation

- Update `README.md` if you add user-facing features
- Add docstrings to public classes and functions
- Configuration changes should be reflected in `config/klaus.yaml`

## Pull Request Process

1. Fork the repo and create a feature branch from `main`
2. Make your changes following the standards above
3. Add or update tests as needed
4. Run the full check locally:
   ```bash
   uv run ruff check src/ tests/ && uv run pytest
   ```
5. Push your branch and open a PR
6. CI will automatically run lint and tests
7. Address any review feedback

## Containers

We use Podman (not Docker). Container files are named `Containerfile`.

```bash
podman build -f Containerfile -t klaus .
podman-compose up -d
podman-compose down
```

## Architecture Decisions

Key design choices to be aware of:

- **Local-first**: Local model backends are always preferred over cloud unless explicitly overridden
- **PostgreSQL + pgvector**: All persistence (memory tree, conversations, routing rules, vector embeddings) lives in PostgreSQL. Embeddings enable semantic memory search
- **Memory tree**: All persistent state lives in a hierarchical tree — new capabilities plug into it as branches
- **Superpowers**: Every new capability is a `Superpower` subclass that registers tools and memory (built-ins: MCP bridge, memory tools, skills system, image generation)
- **Skills system**: Hermes-inspired self-improving skills — the agent creates, reuses, and improves procedures automatically
- **LangChain/LangGraph**: Model abstraction and agent orchestration use the LangChain ecosystem
- **React + Tailwind frontend**: The dashboard is a React + Vite project (`ui/`) with Tailwind CSS and React Flow for the pipeline visualization. `npm run dev` gives HMR; `npm run build` outputs to `src/klaus/ui/dist/` for the backend to serve
