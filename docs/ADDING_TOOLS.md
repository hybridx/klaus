# Adding Tools (Superpowers)

Every capability in klaus is a **Superpower** — a self-contained plugin that bundles LangChain tools, lifecycle hooks, and its own branch in the memory tree. This guide walks through creating one from scratch.

## Concepts

| Concept | What it means |
|---------|---------------|
| **Superpower** | A class that provides one or more tools to the agent |
| **Tool** | A LangChain `StructuredTool` the agent can call during a ReAct loop |
| **Memory branch** | Each superpower gets `/superpowers/{name}` in the memory tree |
| **Registry** | The `SuperpowerRegistry` manages activation, tool collection, and lifecycle |

## Quick Start

Create `src/klaus/superpowers/builtin/web_search.py`:

```python
from __future__ import annotations

from langchain_core.tools import StructuredTool

from klaus.superpowers.base import Superpower


class WebSearch(Superpower):
    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for current information"

    @property
    def tags(self) -> list[str]:
        return ["search", "web", "external"]

    def get_tools(self) -> list[StructuredTool]:
        async def search(query: str) -> str:
            """Search the web and return relevant results."""
            # Your implementation here
            return f"Results for: {query}"

        return [
            StructuredTool.from_function(
                coroutine=search,
                name="web_search",
                description="Search the web for current information",
            ),
        ]
```

Register it in `src/klaus/app.py` inside the lifespan function:

```python
from klaus.superpowers.builtin.web_search import WebSearch

await registry.register(WebSearch())
```

That's it. The agent can now call `web_search(query="...")` in its ReAct loop.

## The Superpower Base Class

Every superpower extends `klaus.superpowers.base.Superpower`:

```python
class Superpower(ABC):
    # ── Required (abstract) ──────────────────────────
    name: str               # Unique ID, becomes /superpowers/{name}
    description: str        # Human-readable, shown in the UI and memory tree
    get_tools() -> list     # Return LangChain tools the agent can use

    # ── Optional overrides ───────────────────────────
    version: str = "0.1.0"  # Semantic version
    tags: list[str] = []    # For filtering and search
    activate() -> None      # Called on registration (async)
    deactivate() -> None    # Called on removal (async)
    get_status() -> dict    # Dashboard metadata

    # ── Memory helpers (available after registration) ─
    remember(key, content)  # Write to /superpowers/{name}/{key}
    recall(key) -> str      # Read from /superpowers/{name}/{key}
```

## Step-by-Step Guide

### 1. Create the file

Place it in `src/klaus/superpowers/builtin/`. The filename should match the superpower name.

### 2. Define the class

```python
class YourPower(Superpower):
    def __init__(self, some_client=None) -> None:
        super().__init__()
        self._client = some_client
```

Pass dependencies through the constructor — the registry doesn't inject anything automatically.

### 3. Implement `get_tools()`

Tools are async closures wrapped in `StructuredTool.from_function`:

```python
def get_tools(self) -> list[StructuredTool]:
    client = self._client

    async def do_thing(input_text: str, options: str = "") -> str:
        """One-line description shown to the LLM as the tool description."""
        result = await client.process(input_text)
        return str(result)

    async def another_thing(query: str) -> str:
        """Search for something specific."""
        return await client.search(query)

    return [
        StructuredTool.from_function(
            coroutine=do_thing,
            name="do_thing",
            description="Process input text and return results",
        ),
        StructuredTool.from_function(
            coroutine=another_thing,
            name="search_thing",
            description="Search for something specific",
        ),
    ]
```

**Important:** The function's docstring and the `description` parameter both matter — the LLM uses them to decide when to call the tool. Be specific and concise.

### 4. Add lifecycle hooks (optional)

```python
async def activate(self) -> None:
    await super().activate()
    # Validate config, connect clients, create directories
    if not self._api_key:
        logger.warning("No API key configured for %s", self.name)

async def deactivate(self) -> None:
    # Close connections, cleanup
    if self._client:
        await self._client.close()
    await super().deactivate()
```

### 5. Use memory (optional)

After registration, `self._memory` is available:

```python
async def activate(self) -> None:
    await super().activate()
    # Store metadata the agent can read
    self.remember("config", f"API base: {self._base_url}")
    self.remember("usage", "0 calls today")
```

The agent can also access this via memory tools — it sees `/superpowers/your_power/config` in the tree.

### 6. Register in `app.py`

In `src/klaus/app.py`, inside the `async def lifespan(app)` function, after the superpowers section:

```python
from klaus.superpowers.builtin.your_power import YourPower

await registry.register(YourPower(client=some_client))
```

### 7. Write tests

Create `tests/test_your_power.py`:

```python
import pytest
from klaus.superpowers.builtin.your_power import YourPower


class TestYourPower:
    def test_name(self):
        p = YourPower()
        assert p.name == "your_power"

    def test_tools_returned(self):
        p = YourPower()
        tools = p.get_tools()
        assert len(tools) >= 1
        names = [t.name for t in tools]
        assert "do_thing" in names

    async def test_tool_execution(self):
        p = YourPower(client=MockClient())
        tools = p.get_tools()
        result = await tools[0].ainvoke({"input_text": "hello"})
        assert "hello" in result
```

## Patterns from Existing Superpowers

### Accessing the database (MemoryTools)

Pass `db` through the constructor for embedding or direct DB access:

```python
class MyPower(Superpower):
    def __init__(self, db=None):
        super().__init__()
        self._db = db
```

### Saving files to disk (ImageGeneration)

Create a data directory in `activate()` and serve files via the `/api/images` static mount:

```python
_OUTPUT_DIR = Path("data/outputs")

async def activate(self) -> None:
    await super().activate()
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
```

### Embedding knowledge eagerly (Skills)

If your tool writes to the memory tree and you want it searchable immediately:

```python
async def create_something(name: str, content: str) -> str:
    mm.put(f"/knowledge/my_data/{name}", content)
    await mm.flush_embeddings()  # Index into pgvector right away
    return f"Created {name}"
```

### Accessing external APIs (ImageGeneration)

Read tokens from environment variables, warn on activation if missing:

```python
def __init__(self):
    super().__init__()
    self._token = os.getenv("MY_API_TOKEN")

async def activate(self) -> None:
    await super().activate()
    if not self._token:
        logger.warning("MY_API_TOKEN not set — %s will be limited", self.name)
```

## What Happens at Runtime

1. `app.py` calls `registry.register(YourPower())`
2. Registry calls `bind_memory()` → your superpower gets access to the memory tree
3. Registry calls `activate()` → your setup hook runs
4. Registry writes metadata to `/superpowers/{name}` in the memory tree
5. On every chat request, `klausAgent._collect_tools()` calls `registry.collect_tools()` which calls `get_tools()` on every active superpower
6. LangGraph's ReAct loop can now invoke your tools
7. Tool results are streamed back to the UI with input/output visibility

## Files to Touch

| File | What to change |
|------|----------------|
| `src/klaus/superpowers/builtin/your_power.py` | Create your superpower class |
| `src/klaus/app.py` | Import and register it in the lifespan function |
| `tests/test_your_power.py` | Add tests |
| `config/klaus.yaml` | Add config section if your tool needs settings |
| `.env.example` | Add env var examples if needed |
| `README.md` | Mention the new capability |
| `CONTRIBUTING.md` | Update if it changes the contributor workflow |
