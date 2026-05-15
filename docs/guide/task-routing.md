# Task Routing

klaus uses a **local-first task router** that selects the best model backend based on the type of request.

## How It Works

1. Every incoming chat message is classified into a **task type** (coding, creative, analysis, chat, etc.)
2. The router checks for a user-defined **routing rule** for that task
3. If no rule exists, the router selects a backend based on **locality preference** (local first, cloud fallback)
4. The chosen backend and model are used to rebuild the LangGraph agent for this request

```
User message: "Write a Python sort function"
       │
       ▼
TaskRouter.classify("Write a Python sort function")
       │  → task = "coding"
       ▼
TaskRouter.resolve("coding")
       │  → Check routing_rules table
       │  → Found: { preferred_backend: "ollama", preferred_model: "granite-code:8b" }
       ▼
Decision(backend="ollama", model="granite-code:8b")
       │
       ▼
klausAgent._build_agent(backend="ollama", model="granite-code:8b")
```

## Configuration

### Via `klaus.yaml`

```yaml
task_routing:
  coding:
    preferred_backend: ollama
    preferred_model: granite-code:8b
  creative:
    preferred_backend: gemini
    preferred_model: gemini-2.5-flash
  analysis:
    preferred_backend: huggingface
    preferred_model: Qwen/Qwen3-235B-A22B
  chat:
    preferred_backend: ollama
    preferred_model: llama3.2
```

### Via REST API

```bash
# Set a routing rule
curl -X POST http://localhost:8000/api/routing/rules \
  -H 'Content-Type: application/json' \
  -d '{"task": "coding", "rule": {"preferred_backend": "ollama", "preferred_model": "granite-code:8b"}}'

# List all rules
curl http://localhost:8000/api/routing/rules

# Delete a rule
curl -X DELETE http://localhost:8000/api/routing/rules/coding
```

Rules set via API are persisted in PostgreSQL (`routing_rules` table) and survive restarts.

### Via the UI

The **Routing** page in the dashboard shows all rules and lets you add, edit, or delete them. Rules changed in the UI take effect immediately for the next chat message.

## Locality Preference

Each backend has a `locality` setting (`local` or `cloud`). The router prefers local backends to minimize latency and keep data on-device:

| Priority | Condition |
|----------|-----------|
| 1 | Explicit routing rule exists → use it |
| 2 | Local backend is healthy → use it |
| 3 | Cloud backend is healthy → fall back |
| 4 | No backend available → error |

## Chat UI Integration

When a model is routed, the chat interface shows:
- The **model badge** next to the response (e.g., "granite-code:8b via ollama")
- Clicking the badge navigates to the Routing page

This makes routing transparent to the user.
