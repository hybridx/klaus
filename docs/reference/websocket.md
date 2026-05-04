# WebSocket Protocol

The real-time WebSocket endpoint provides streaming chat, tool visibility, and system events.

## Connection

```
ws://localhost:8000/api/events/ws
```

From the React frontend:

```typescript
const ws = new WebSocket('ws://localhost:8000/api/events/ws');
```

## Client → Server Messages

### `chat`

Start a new chat interaction:

```json
{
  "type": "chat",
  "id": "session-uuid",
  "messages": [
    { "role": "user", "content": "How do I sort a list in Python?" }
  ],
  "task": "coding"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"chat"` | Yes | Message type |
| `id` | `string` | Yes | Session ID |
| `messages` | `Message[]` | Yes | Full conversation so far |
| `task` | `string` | No | Task type for routing |

## Server → Client Messages

### `chat.token`

Streaming token from the LLM:

```json
{
  "type": "chat.token",
  "content": "Here"
}
```

### `chat.done`

Response complete:

```json
{
  "type": "chat.done",
  "content": "Here is how to sort a list in Python..."
}
```

### `chat.error`

An error occurred:

```json
{
  "type": "chat.error",
  "content": "Failed to connect to Ollama backend"
}
```

### `mcp.tool_called`

A tool is being invoked (before result):

```json
{
  "type": "mcp.tool_called",
  "tool": "remember",
  "name": "remember",
  "args": { "path": "python/tips", "content": "List comprehensions" }
}
```

### `tool.result`

A tool has returned its result:

```json
{
  "type": "tool.result",
  "tool": "remember",
  "content": "Stored at /knowledge/python/tips"
}
```

### `chat.routing`

Routing decision for this request:

```json
{
  "type": "chat.routing",
  "backend": "ollama",
  "model": "granite-code:8b",
  "task": "coding"
}
```

## Message Flow

```
Client                          Server
  │                               │
  │──── { type: "chat", ... } ───▶│
  │                               │  classify task
  │                               │  resolve routing
  │◀── { type: "chat.routing" } ──│
  │                               │  build agent
  │                               │  ReAct loop starts
  │◀── { type: "mcp.tool_called"}│  tool invocation
  │◀── { type: "tool.result" }  ──│  tool result
  │◀── { type: "chat.token" }   ──│  streaming tokens...
  │◀── { type: "chat.token" }   ──│
  │◀── { type: "chat.token" }   ──│
  │◀── { type: "chat.done" }    ──│  response complete
  │                               │
```

## Reconnection

The `useWebSocket` hook implements auto-reconnection with exponential backoff. If the connection drops, the hook reconnects and the UI shows a brief status indicator.
