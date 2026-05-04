# Memory System

klaus uses a **hierarchical memory tree** backed by **PostgreSQL + pgvector** for persistent, searchable knowledge. The agent reads from memory on every request and writes to it when it learns something new.

## Overview

```
┌──────────────────────────────────────────────────────────┐
│                     Memory Tree                           │
│                                                           │
│  /                                                        │
│  ├── /knowledge          Agent's learned knowledge        │
│  │   ├── /skills         Hermes-style procedures          │
│  │   ├── /user           User preferences/facts           │
│  │   └── /system         System-generated insights        │
│  ├── /conversations      Per-session summaries            │
│  │   └── /session-id     Latest exchange snapshot         │
│  └── /superpowers        Registered capabilities          │
│      ├── /mcp            MCP bridge metadata              │
│      ├── /memory         Memory tools description         │
│      ├── /skills          Skills superpower metadata      │
│      └── /image_generation Image gen description          │
│                                                           │
│  In-memory tree ←→ PostgreSQL (JSONB blob)                │
│                                                           │
│  /knowledge + /user paths also indexed as                 │
│  384-dim vectors in pgvector for semantic search           │
└──────────────────────────────────────────────────────────┘
```

## Components

### MemoryNode

The atomic unit of the tree. Each node can be both a branch (has children) and a leaf (has content):

```python
@dataclass
class MemoryNode:
    id: str                    # Short UUID (12 hex chars)
    name: str                  # Node name (path segment)
    content: str               # Stored text content
    metadata: dict             # Arbitrary key-value metadata
    tags: list[str]            # For filtering and search
    children: dict[str, Node]  # Child nodes by name
    created_at: float          # Unix timestamp
    updated_at: float          # Unix timestamp
    access_count: int          # How often accessed
    embedding: list[float]     # Optional cached embedding
```

### MemoryTree

Hierarchical data structure with filesystem-like path operations:

| Method | Description |
|--------|-------------|
| `put(path, content, metadata, tags)` | Create/update node at path (creates intermediates) |
| `get(path) → MemoryNode?` | Retrieve node by path |
| `delete(path) → bool` | Remove node and its subtree |
| `move(src, dst) → bool` | Move subtree to new path |
| `ls(path) → list[str]` | List child names |
| `walk(path) → list[(path, node)]` | DFS traversal |
| `search(query, root_path, max_results)` | Keyword search with TF-style scoring |
| `recent(root_path, n)` | Most recently updated nodes |
| `context_for(path, depth)` | Ancestors + siblings for context injection |
| `to_dict() / from_dict()` | JSON serialization |

**`put` behavior:** Like `mkdir -p` — creates all intermediate nodes. Supports `merge=True` to append content and union tags instead of replacing.

### MemoryManager

Owns the tree and handles persistence. All tree access should go through this:

| Method | Description |
|--------|-------------|
| `startup()` | Load tree from store (PostgreSQL) |
| `shutdown()` | Flush embeddings + save tree |
| `put(path, content, **kwargs)` | Write to tree, mark dirty, queue for embedding |
| `get(path)` | Read from tree |
| `delete(path)` | Remove from tree |
| `search(query, ...)` | Keyword search |
| `save()` | Persist tree to store |
| `maybe_save()` | Auto-save if dirty + interval elapsed; always flushes embeddings |
| `flush_embeddings()` | Index queued paths into pgvector |

**Embedding queue:** When `put()` is called with a path starting with `/knowledge` or `/user`, the `(path, content)` pair is queued. On `maybe_save()` or `flush_embeddings()`, queued items are embedded and stored in PostgreSQL.

### MemoryIndex

Search engine that combines keyword matching with semantic search:

| Method | Description |
|--------|-------------|
| `search(query, root_path, tags, max_results)` | Keyword + tag + recency scoring |
| `semantic_search(query, limit)` | pgvector cosine similarity search |
| `hybrid_search(query, root_path, max_results)` | Blended keyword + semantic results |
| `gather_context(query, conversation_path)` | Build context string for agent injection |
| `index_node(path, content)` | Embed and store a single node |
| `index_tree(root_path)` | Batch-embed all nodes under a path |

### EmbeddingModel

Lazy-loaded sentence transformer for generating 384-dimensional vectors:

- **Model:** `sentence-transformers/all-MiniLM-L6-v2`
- **Dimensions:** 384
- **Size:** ~80MB, CPU-friendly
- **Loading:** First `encode()` call loads the model (cached thereafter)
- **Fallback:** If `sentence-transformers` isn't installed, encoding returns `[]` and search degrades to keyword-only

## Data Flow

### Writing knowledge

```
Agent calls remember("python/tips", "Use list comprehensions...")
    │
    ▼
MemoryManager.put("/knowledge/python/tips", content)
    │
    ├── MemoryTree.put() — creates node, updates timestamps
    ├── mark_dirty() — flags tree for persistence
    └── Queue ("/knowledge/python/tips", content) for embedding
    │
    ▼
flush_embeddings()
    │
    ├── EmbeddingModel.encode(content) → [0.12, -0.34, ...] (384 floats)
    └── Database.save_embedding(path, content[:500], vector)
         └── PostgreSQL: INSERT INTO embeddings (path, content, embedding)
```

### Reading knowledge (agent context)

```
User sends message: "How do I write Python efficiently?"
    │
    ▼
klausAgent.stream() → _build_memory_context(messages)
    │
    ▼
MemoryIndex.gather_context("How do I write Python efficiently?")
    │
    ├── tree.context_for(conversation_path) — recent conversation nodes
    ├── hybrid_search(query, root_path="/knowledge")
    │   ├── search() — keyword: "python", "efficiently" → scored results
    │   └── semantic_search() — embed query → pgvector cosine distance
    │       └── Database.search_embeddings(query_vec, limit=5)
    │           └── SELECT ... ORDER BY embedding <=> $1 LIMIT 5
    │   └── Merge: keyword * 0.4 + semantic * 10 * 0.6
    └── /superpowers children → capabilities list
    │
    ▼
Context string injected into system prompt:
  "[memory:/knowledge/python/tips] Use list comprehensions..."
```

### Persistence

```
MemoryManager.save()
    │
    ▼
PostgresStore.save(tree)
    └── Database.save_memory_tree(tree.to_dict())
        └── UPSERT INTO memory_tree (id=1, data=JSONB, saved_at=NOW)

MemoryManager.startup()
    │
    ▼
PostgresStore.load()
    └── Database.load_memory_tree()
        └── SELECT data FROM memory_tree WHERE id = 1
            └── MemoryTree.from_dict(data) — reconstructs tree
```

## PostgreSQL Schema

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Full tree as a single JSONB blob (loaded into memory on startup)
CREATE TABLE memory_tree (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    data     JSONB NOT NULL,
    saved_at DOUBLE PRECISION NOT NULL
);

-- Chat messages for conversation persistence
CREATE TABLE conversations (
    id         SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    model      TEXT,
    backend    TEXT,
    created_at DOUBLE PRECISION NOT NULL
);

-- Task routing rules
CREATE TABLE routing_rules (
    task       TEXT PRIMARY KEY,
    rule       JSONB NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);

-- Vector embeddings for semantic search (pgvector)
CREATE TABLE embeddings (
    id         SERIAL PRIMARY KEY,
    path       TEXT NOT NULL,          -- Memory tree path
    content    TEXT NOT NULL,          -- First 500 chars of content
    embedding  vector(384) NOT NULL,  -- all-MiniLM-L6-v2 output
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
);
```

## Hybrid Search Scoring

The `hybrid_search` method blends keyword and semantic results:

1. **Keyword search** scores based on:
   - Term frequency in content and name (name matches boosted)
   - Tag matches
   - Recency weight: `exp(-age / 3600)` (half-life = 1 hour)
   - Access count bonus: `log(1 + access_count) * 0.1`

2. **Semantic search** uses pgvector cosine distance:
   - Query and content both embedded with all-MiniLM-L6-v2
   - `similarity = 1 - cosine_distance`

3. **Merge:**
   - Nodes found by both: `score = keyword * 0.4 + semantic * 10 * 0.6`
   - Semantic-only nodes: `score = similarity * 10`
   - Sorted descending, capped at `max_results`

## Agent Tools

The agent has direct access to memory through these tools (provided by `MemoryTools` superpower):

| Tool | Description |
|------|-------------|
| `remember(path, content)` | Store at `/knowledge/{path}`, immediately flush to pgvector |
| `recall(path)` | Read from `/knowledge/{path}` |
| `search_memory(query)` | Hybrid search across the entire tree |
| `list_memory(path)` | List children at a path |

The **Skills** superpower also writes to `/knowledge/skills/` with versioned procedures.

## Self-Improvement Loop

After complex interactions (3+ tool calls), the agent stores a reflection nudge:

```python
# In klausAgent.stream():
if tool_call_count >= 3:
    self._memory.put(
        "/knowledge/system/last_complex_task",
        f"Complex task ({tool_call_count} tool calls): {summary}... → Consider creating a skill.",
    )
```

This nudge appears in the memory context for subsequent requests, encouraging the agent to create reusable skills.

## Knowledge Graph UI

The Knowledge page (`ui/src/pages/Knowledge.tsx`) visualizes the memory tree as a force-directed graph:

- **Nodes** are circles, color-coded by branch (`/knowledge` = indigo, `/conversations` = green, `/superpowers` = amber)
- **Edges** connect parent → child
- **Click** a node to see its full content in a side panel (fetched via `GET /api/memory/get?path=...`)
- **Data** comes from `GET /api/memory/graph` which returns a flat node list

## Configuration

In `config/klaus.yaml`:

```yaml
database:
  url: postgresql://klaus:klaus@localhost:5432/klaus
  pool_min: 2
  pool_max: 10
```

Or via environment variable:

```
DATABASE_URL=postgresql://klaus:klaus@localhost:5432/klaus
```

## Files

| File | Purpose |
|------|---------|
| `src/klaus/memory/tree.py` | `MemoryNode` and `MemoryTree` data structures |
| `src/klaus/memory/store.py` | `MemoryManager`, store backends (`JsonFileStore`, `PostgresStore`) |
| `src/klaus/memory/index.py` | `MemoryIndex`, `EmbeddingModel`, search algorithms |
| `src/klaus/db.py` | `Database` class — PostgreSQL connection pool, schema, queries |
| `src/klaus/superpowers/builtin/memory_tools.py` | Agent-facing memory tools |
| `src/klaus/superpowers/builtin/skills.py` | Skills stored in `/knowledge/skills/` |
| `src/klaus/agents/graph.py` | Memory context injection in `_build_memory_context` |
| `ui/src/pages/Knowledge.tsx` | Knowledge graph visualization |
