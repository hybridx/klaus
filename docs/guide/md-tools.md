# Markdown-Based Tools

klaus supports defining lightweight tools using simple Markdown files — no Python module or superpower class needed. Drop a `.md` file in the tools directory and it becomes available to the agent at startup.

## Quick Start

Create a file in `data/tools/`:

```markdown
# Tool: greet

Say hello to someone by name.

## Parameters
- name (string, required): The person's name
- language (string): Language for greeting (default: English)

## Implementation
```python
async def run(name: str, language: str = "English") -> str:
    greetings = {"English": "Hello", "Spanish": "Hola", "French": "Bonjour"}
    greeting = greetings.get(language, "Hello")
    return f"{greeting}, {name}!"
```
```

Restart klaus and the tool is automatically registered.

## File Format

Every MD tool file follows this structure:

### 1. Heading — Tool Name

```markdown
# Tool: tool_name
```

The first line must be a level-1 heading starting with `Tool:`. The name should be `snake_case` with no spaces.

### 2. Description

Lines between the heading and the first `##` become the tool's description, shown to the LLM when it decides which tool to call.

```markdown
Search the web for information and return relevant results.
```

### 3. Parameters Section

```markdown
## Parameters
- query (string, required): The search query
- max_results (integer): Maximum number of results (optional, defaults to 5)
```

Each parameter follows this syntax:

```
- param_name (type, required): Description
- param_name (type): Description
```

Supported types:

| Type | Python equivalent |
|------|------------------|
| `string` / `str` | `str` |
| `integer` / `int` | `int` |
| `number` / `float` | `float` |
| `boolean` / `bool` | `bool` |

Omitting `required` makes the parameter optional (defaults to `None`).

### 4. Implementation Section

````markdown
## Implementation
```python
async def run(**kwargs) -> str:
    # Your tool logic here
    return "result"
```
````

The code block must define an `async def run(...)` function that returns a string. You can:

- Import standard library modules
- Use the exact parameter names from the Parameters section
- Return any string result

::: warning
The implementation code is executed with `exec()`. Only use trusted tool files. Do not load MD tools from untrusted sources.
:::

## Configuration

Set the tools directory in `config/klaus.yaml`:

```yaml
orchestrator:
  md_tools_dir: data/tools
```

The default directory is `data/tools` relative to the project root.

## Built-in Example Tools

klaus ships with three example MD tools:

### `calculator.md`
Evaluates mathematical expressions using Python's math library.

### `date_time.md`
Gets current date/time or performs date calculations.

### `text_transform.md`
Applies string operations (uppercase, lowercase, slug, word count, etc.).

## How MD Tools Are Loaded

1. At startup, `app.py` calls `load_md_tools()` from `src/klaus/mcp/md_tools.py`
2. Each `.md` file in the configured directory is parsed
3. Valid tools are converted into LangChain `StructuredTool` instances
4. The tools are passed to the `MCPBridge` superpower, making them available alongside MCP server tools
5. The agent sees them as regular tools during execution

## API

MD tools appear in the superpowers tools list:

```bash
curl http://localhost:8000/api/superpowers/tools
```

```json
{
  "tools": [
    { "name": "calculator", "description": "Evaluate a mathematical expression..." },
    { "name": "date_time", "description": "Get the current date, time, or perform..." },
    { "name": "text_transform", "description": "Transform text by applying common..." }
  ]
}
```

## Tips

- **Keep tools focused** — one tool per file, doing one thing well
- **Write clear descriptions** — the LLM uses the description to decide when to call the tool
- **Test locally** — the `run()` function should work standalone
- **No external dependencies** — MD tools can only use the Python standard library and packages already installed in the klaus environment
