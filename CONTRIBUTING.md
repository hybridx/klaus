# Contributing to klaus

Thanks for your interest in contributing. This guide covers everything you need to get started.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)
- [Podman](https://podman.io/) (for container builds, optional)
- [Ollama](https://ollama.ai/) (for local model testing, optional)

## Setup

```bash
git clone <repo-url> && cd klaus
uv run klaus-dev
```

`uv` creates the virtual environment and installs all dependencies automatically on first run.

## Development

```bash
uv run klaus-dev              # start dev server with auto-reload
uv run ruff check src/ tests/ # run ruff linter
uv run ruff check --fix src/  # auto-fix lint issues
uv run pytest                 # run test suite
```

The dev server runs at `http://localhost:8000/` with debug logging and hot reload on file changes.

## Project Layout

```
src/klaus/
├── agents/          LangGraph agent, tool bridges, Langfuse tracing
├── api/             FastAPI routes (chat, models, mcp, routing, memory, superpowers)
├── config/          Pydantic settings, YAML loader
├── events/          WebSocket event bus
├── mcp/             Dynamic MCP server manager
├── memory/          Tree-structured persistent memory
├── models/          Model registry + LangChain backends
├── routing/         Task-based model routing (local-first)
├── superpowers/     Plugin system for capabilities
└── ui/              Lit web components dashboard
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
- **Memory tree**: All persistent state lives in a hierarchical tree — new capabilities plug into it as branches
- **Superpowers**: Every new capability is a `Superpower` subclass that registers tools and memory
- **LangChain/LangGraph**: Model abstraction and agent orchestration use the LangChain ecosystem
- **No build step for UI**: The dashboard uses Lit web components loaded from CDN — no npm/webpack needed
