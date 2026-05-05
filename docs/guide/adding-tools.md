# Adding Tools

There are **two approaches** to give the agent new tools. Pick the one that fits your use case:

| Approach | When to use | Effort | Restart needed? |
|----------|------------|--------|-----------------|
| **Markdown file** | Simple, standalone tools using stdlib or installed packages | Drop a `.md` file | Yes (restart) |
| **Superpower class** | Multi-tool bundles, lifecycle hooks, memory integration, external clients | Write a Python class + register | Yes (restart) |

---

## Approach 1: Markdown File (No Code Changes)

Create a `.md` file in `data/tools/` and restart. The tool is automatically loaded and available to the agent.

### Working Example: `data/tools/word_counter.md`

````markdown
# Tool: word_counter

Count the number of words, sentences, and characters in a piece of text.

## Parameters
- text (string, required): The text to analyze

## Implementation
```python
import re

async def run(text: str) -> str:
    words = len(text.split())
    sentences = len([s for s in re.split(r'[.!?]+', text) if s.strip()])
    chars = len(text)
    return f"Words: {words}, Sentences: {sentences}, Characters: {chars}"
```
````

That's it. After restarting klaus, the agent can call `word_counter(text="...")`.

### File Format

```
# Tool: tool_name          ← snake_case name (required)
Description for the LLM.   ← free text until next ##

## Parameters               ← optional section
- name (type, required): Description
- name (type): Description  ← omit "required" for optional params

## Implementation           ← optional section
```python
async def run(**kwargs) -> str:
    return "result"
```
```

Supported types: `string`, `integer`, `number`, `boolean`.

If you omit `## Implementation`, a stub function is created that echoes the arguments.

### Limitations

- Tools can only use the Python standard library and packages already installed in the klaus environment
- No lifecycle hooks or memory tree access
- The implementation runs via `exec()` — only use trusted files

For full details, see the [MD-Based Tools guide](./md-tools.md).

---

## Approach 2: Superpower Class (Full Power)

For tools that need external API clients, memory integration, multi-tool bundles, or lifecycle hooks.

### Working Example: `src/klaus/superpowers/builtin/url_fetch.py`

This is a complete, working superpower that fetches and summarizes web pages:

```python
from __future__ import annotations

import httpx
from langchain_core.tools import StructuredTool

from klaus.superpowers.base import Superpower


class URLFetch(Superpower):
    def __init__(self) -> None:
        super().__init__()
        self._http: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "url_fetch"

    @property
    def description(self) -> str:
        return "Fetch and extract text from URLs"

    @property
    def tags(self) -> list[str]:
        return ["web", "fetch", "http"]

    async def activate(self) -> None:
        await super().activate()
        self._http = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
        self.remember("config", "URL fetcher ready, 15s timeout")

    async def deactivate(self) -> None:
        if self._http:
            await self._http.aclose()
        await super().deactivate()

    def get_tools(self) -> list[StructuredTool]:
        http = self._http

        async def fetch_url(url: str, max_chars: int = 5000) -> str:
            """Fetch a URL and return its text content."""
            if not http:
                return "Error: HTTP client not initialized"
            try:
                resp = await http.get(url)
                resp.raise_for_status()
                text = resp.text[:max_chars]
                return text
            except Exception as exc:
                return f"Error fetching {url}: {exc}"

        return [
            StructuredTool.from_function(
                coroutine=fetch_url,
                name="fetch_url",
                description="Fetch a URL and return its text content (HTML stripped)",
            ),
        ]
```

Register it in `src/klaus/app.py`:

```python
from klaus.superpowers.builtin.url_fetch import URLFetch

await registry.register(URLFetch())
```

### Step-by-Step

1. **Create the file** in `src/klaus/superpowers/builtin/`
2. **Extend `Superpower`** — implement `name`, `description`, and `get_tools()`
3. **Add lifecycle hooks** (optional) — `activate()` for setup, `deactivate()` for cleanup
4. **Use memory** (optional) — `self.remember(key, content)` and `self.recall(key)`
5. **Register in `app.py`** — import and `await registry.register(YourPower())`
6. **Write tests** in `tests/test_your_power.py`

### The Superpower Base Class

```python
class Superpower(ABC):
    # Required
    name: str               # Unique ID, becomes /superpowers/{name}
    description: str        # Human-readable, shown in the UI
    get_tools() -> list     # Return LangChain tools the agent can use

    # Optional overrides
    version: str = "0.1.0"
    tags: list[str] = []
    activate() -> None      # Called on registration (async)
    deactivate() -> None    # Called on removal (async)

    # Memory helpers (available after registration)
    remember(key, content)  # Write to /superpowers/{name}/{key}
    recall(key) -> str      # Read from /superpowers/{name}/{key}
```

### Patterns from Built-in Superpowers

**Accessing the database:**

```python
class MyPower(Superpower):
    def __init__(self, db=None):
        super().__init__()
        self._db = db
```

**Reading API keys from environment:**

```python
def __init__(self):
    super().__init__()
    self._token = os.getenv("MY_API_TOKEN")
```

**Embedding knowledge into memory:**

```python
async def create_knowledge(name: str, content: str) -> str:
    mm.put(f"/knowledge/my_data/{name}", content)
    await mm.flush_embeddings()
    return f"Created {name}"
```

### Runtime Flow

1. `app.py` calls `registry.register(YourPower())`
2. Registry binds memory → superpower gets memory access
3. Registry calls `activate()` → your setup hook runs
4. On every chat, `klausAgent._collect_tools()` gathers tools from all active superpowers
5. LangGraph's ReAct loop invokes your tools
6. Results stream back to the UI

---

## Which Approach Should I Use?

| Scenario | Use |
|----------|-----|
| Quick utility (calculator, text transform, date) | Markdown file |
| Wraps an external API (GitHub, Jira, Slack) | Superpower class |
| Needs API keys or auth tokens | Superpower class |
| Needs to read/write memory | Superpower class |
| Bundles multiple related tools | Superpower class |
| Prototype before building a full superpower | Markdown file |

## Files to Touch

| File | What to change |
|------|----------------|
| `data/tools/your_tool.md` | Create an MD-based tool (no code changes) |
| `src/klaus/superpowers/builtin/your_power.py` | Create a superpower class |
| `src/klaus/app.py` | Import and register (superpowers only) |
| `tests/test_your_power.py` | Add tests |
| `config/klaus.yaml` | Add config section if needed |
| `.env.example` | Add env var examples if needed |
