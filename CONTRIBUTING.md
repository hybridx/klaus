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

PostgreSQL with pgvector is required. The default connection URL (`postgresql://klaus:klaus@localhost:5432/klaus`) works out of the box with the provided `docker-compose.yml`. Override it via `DATABASE_URL` in `.env` or `database.url` in `config/klaus.yaml`.

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
│   ├── hooks/           React hooks (useWebSocket, useTheme)
│   ├── components/      Shared components (Layout, Sidebar, Markdown)
│   └── pages/           Page components (Chat, Knowledge, Flow, Models, Routing, Activity)
├── index.html
├── vite.config.ts
└── tsconfig.json

src/klaus/           Backend (Python + FastAPI)
├── agents/          LangGraph agent, tool bridges, Langfuse tracing
├── api/             FastAPI routes (chat, models, mcp, routing, memory, superpowers)
├── config/          Pydantic settings, YAML loader
├── events/          WebSocket event bus
├── mcp/             Dynamic MCP server manager
├── memory/          Tree-structured persistent memory
├── models/          Model registry + LangChain backends (Ollama, Gemini, HuggingFace)
├── routing/         Task-based model routing (local-first)
├── superpowers/     Plugin system (MCP bridge, memory, skills, image gen)
└── ui/dist/         Built frontend output (gitignored)
```

## How to Contribute

### Adding a New Model Backend

1. Create `src/klaus/models/backends/your_backend.py`
2. Implement `generate()`, `stream()`, `list_models()`, `health()`, and `get_chat_model()` — follow the pattern in `ollama.py`
3. Register the factory in `src/klaus/models/registry.py` → `BACKEND_FACTORIES`
4. Add a config block in `config/klaus.yaml`
5. Write tests in `tests/test_backends.py`

### Adding a New Superpower

1. Create `src/klaus/superpowers/builtin/your_power.py`
2. Subclass `Superpower` and implement `name`, `description`, and `get_tools()`
3. Register it in `src/klaus/app.py` → lifespan function
4. Write tests in `tests/test_superpowers.py`

Example skeleton:

```python
from klaus.superpowers.base import Superpower
from langchain_core.tools import StructuredTool

class WebSearch(Superpower):
    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for current information"

    @property
    def tags(self) -> list[str]:
        return ["search", "web"]

    def get_tools(self) -> list[StructuredTool]:
        async def search(query: str) -> str:
            ...
        return [StructuredTool.from_function(coroutine=search, name="web_search", description="...")]
```

### Adding API Endpoints

1. Create a route file in `src/klaus/api/routes/`
2. Use `get_state()` from `klaus.api.deps` to access subsystems
3. Register the router in `src/klaus/app.py` → `create_app()`
4. Write tests in `tests/test_api.py`

### Working on the Frontend

The UI is a React + Vite + Tailwind CSS project in `ui/`. The Pipeline page uses [React Flow](https://reactflow.dev/) for the agent→model flow visualization.

**Adding a new page:**

1. Create `ui/src/pages/YourPage.tsx` as a React component
2. Add the page ID to the `Page` union type in `App.tsx`
3. Add a nav entry in `components/Layout.tsx` → `NAV` array
4. Render it conditionally in `App.tsx`

Example skeleton:

```tsx
import { useEffect, useState } from 'react';

export default function YourPage() {
  const [data, setData] = useState([]);

  useEffect(() => {
    fetch('/api/your-endpoint')
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  return (
    <div className="h-full overflow-y-auto p-4">
      <p className="text-[11px] text-gray-400">Description.</p>
      {/* your content */}
    </div>
  );
}
```

**Styling guidelines:**

- Use Tailwind CSS utility classes — avoid inline styles or CSS modules
- Reference theme tokens from `index.css` (e.g. `bg-surface`, `text-accent`, `border-border`)
- Dark mode is handled via the `.dark` class on `<html>` — use `dark:` prefixes where needed

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
