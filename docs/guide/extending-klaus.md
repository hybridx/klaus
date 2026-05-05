# Extending klaus — Developer Guide

This guide shows you how to add new capabilities to klaus. Every extension follows the same pattern: give the agent new tools, new knowledge, or new specialist agents.

## Quick Reference

| I want to... | Approach | Files | Restart? |
|-------------|----------|-------|----------|
| Add a simple tool | MD file | `data/tools/my_tool.md` | Yes |
| Add a specialist agent | MD file | `data/agents/my_agent.md` | Yes |
| Add a full-featured superpower | Python class | `src/klaus/superpowers/builtin/my_power.py` + `app.py` | Yes |
| Add a model backend | Python class | `src/klaus/models/backends/my_backend.py` + `registry.py` | Yes |
| Connect an MCP server | JSON config | `mcp.json` or API call | No (API) / Yes (config) |

## Example: Adding GitHub Support

This walkthrough builds a complete GitHub integration as a superpower — from scanning a codebase to storing it in vector embeddings to generating patches for bugs.

### What we're building

A `github_codebase` superpower that:
1. Clones or fetches a GitHub repository
2. Indexes the codebase into vector embeddings in the memory tree
3. Provides tools for semantic code search, file reading, and patch generation
4. Can create PRs via the GitHub API

### Step 1: Plan the tools

| Tool | Description |
|------|-------------|
| `github_index_repo` | Clone/fetch a repo and index all source files into memory |
| `github_search_code` | Semantic search across the indexed codebase |
| `github_read_file` | Read a specific file from the repo |
| `github_create_patch` | Generate a diff/patch for a specified change |
| `github_create_pr` | Create a pull request with the generated patch |

### Step 2: Create the superpower

Create `src/klaus/superpowers/builtin/github_codebase.py`:

```python
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from langchain_core.tools import StructuredTool

from klaus.superpowers.base import Superpower


class GitHubCodebase(Superpower):
    """Superpower that indexes GitHub repos into memory
    for semantic search and automated patch generation."""

    def __init__(self, db=None) -> None:
        super().__init__()
        self._db = db
        self._http: httpx.AsyncClient | None = None
        self._token = os.getenv("GITHUB_TOKEN", "")
        self._repos: dict[str, Path] = {}

    @property
    def name(self) -> str:
        return "github_codebase"

    @property
    def description(self) -> str:
        return "Index GitHub repositories and generate patches for bugs"

    @property
    def tags(self) -> list[str]:
        return ["github", "code", "git", "patch"]

    async def activate(self) -> None:
        await super().activate()
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._http = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            timeout=30.0,
        )
        self.remember("status", "GitHub codebase superpower active")

    async def deactivate(self) -> None:
        if self._http:
            await self._http.aclose()
        await super().deactivate()

    def get_tools(self) -> list[StructuredTool]:
        sp = self

        async def github_index_repo(
            repo: str, branch: str = "main", extensions: str = ".py,.ts,.js,.go,.rs,.java"
        ) -> str:
            """Clone a GitHub repo and index source files into vector memory.

            Args:
                repo: GitHub repo in owner/name format (e.g. "hybridx/klaus")
                branch: Branch to index (default: main)
                extensions: Comma-separated file extensions to index
            """
            clone_url = f"https://github.com/{repo}.git"
            tmpdir = Path(tempfile.mkdtemp(prefix="klaus-gh-"))
            try:
                subprocess.run(
                    ["git", "clone", "--depth=1", f"--branch={branch}",
                     clone_url, str(tmpdir)],
                    capture_output=True, text=True, check=True, timeout=120,
                )
            except subprocess.CalledProcessError as e:
                return f"Clone failed: {e.stderr}"

            sp._repos[repo] = tmpdir
            ext_set = set(extensions.split(","))
            indexed = 0

            for fpath in tmpdir.rglob("*"):
                if not fpath.is_file():
                    continue
                if fpath.suffix not in ext_set:
                    continue
                rel = str(fpath.relative_to(tmpdir))
                if any(part.startswith(".") for part in rel.split("/")):
                    continue
                try:
                    content = fpath.read_text(errors="replace")[:50_000]
                except Exception:
                    continue

                if sp._memory:
                    sp._memory.put(
                        f"/knowledge/codebase/{repo}/{rel}",
                        content,
                        tags=["code", "github", repo],
                    )
                    indexed += 1

            if sp._memory:
                await sp._memory.flush_embeddings()

            return (
                f"Indexed {indexed} files from {repo}@{branch}. "
                f"Search with github_search_code(query=..., repo='{repo}')"
            )

        async def github_search_code(query: str, repo: str = "") -> str:
            """Semantic search across an indexed GitHub codebase.

            Args:
                query: Natural language search query
                repo: Limit search to a specific repo (owner/name)
            """
            if not sp._memory:
                return "Memory not available"

            tags = ["code", "github"]
            if repo:
                tags.append(repo)

            results = sp._memory.search(query, tags=tags, limit=8)
            if not results:
                return "No matching code found. Index a repo first with github_index_repo."

            output = []
            for r in results:
                path = r.path.replace("/knowledge/codebase/", "")
                preview = (r.content or "")[:500]
                output.append(f"## {path}\n```\n{preview}\n```")
            return "\n\n".join(output)

        async def github_read_file(repo: str, path: str) -> str:
            """Read a file from an indexed repo.

            Args:
                repo: GitHub repo (owner/name)
                path: File path within the repo
            """
            memory_path = f"/knowledge/codebase/{repo}/{path}"
            if sp._memory:
                node = sp._memory.get(memory_path)
                if node and node.content:
                    return node.content
            return f"File not found: {path} in {repo}. Index the repo first."

        async def github_create_patch(
            repo: str, file_path: str, description: str
        ) -> str:
            """Generate a unified diff patch for a file based on a bug description.

            The LLM analyzes the file content and the bug description,
            then produces a patch. The actual patch generation is done by
            the LLM in the orchestrator — this tool provides the file
            content and metadata for context.

            Args:
                repo: GitHub repo (owner/name)
                file_path: File to patch
                description: Bug description or change request
            """
            content = await github_read_file(repo, file_path)
            if content.startswith("File not found"):
                return content
            return (
                f"## Patch context for {repo}/{file_path}\n\n"
                f"**Bug/Change:** {description}\n\n"
                f"**Current file content ({len(content)} chars):**\n"
                f"```\n{content[:10_000]}\n```\n\n"
                "Generate a unified diff patch to fix this issue. "
                "Use --- a/ and +++ b/ format."
            )

        async def github_create_pr(
            repo: str, title: str, body: str, branch: str = "",
            base: str = "main"
        ) -> str:
            """Create a pull request on GitHub.

            Args:
                repo: GitHub repo (owner/name)
                title: PR title
                body: PR description (markdown)
                branch: Source branch name
                base: Target branch (default: main)
            """
            if not sp._http:
                return "GitHub client not initialized"
            if not sp._token:
                return "GITHUB_TOKEN not set — cannot create PRs"

            resp = await sp._http.post(
                f"/repos/{repo}/pulls",
                json={
                    "title": title, "body": body,
                    "head": branch, "base": base,
                },
            )
            if resp.status_code == 201:
                data = resp.json()
                return f"PR created: {data['html_url']}"
            return f"Failed to create PR: {resp.status_code} {resp.text}"

        return [
            StructuredTool.from_function(
                coroutine=github_index_repo,
                name="github_index_repo",
                description="Clone a GitHub repo and index source files into vector memory",
            ),
            StructuredTool.from_function(
                coroutine=github_search_code,
                name="github_search_code",
                description="Semantic search across indexed GitHub codebases",
            ),
            StructuredTool.from_function(
                coroutine=github_read_file,
                name="github_read_file",
                description="Read a file from an indexed GitHub repo",
            ),
            StructuredTool.from_function(
                coroutine=github_create_patch,
                name="github_create_patch",
                description="Get file content and context for generating a patch",
            ),
            StructuredTool.from_function(
                coroutine=github_create_pr,
                name="github_create_pr",
                description="Create a pull request on GitHub",
            ),
        ]
```

### Step 3: Register it

In `src/klaus/app.py`, add:

```python
from klaus.superpowers.builtin.github_codebase import GitHubCodebase

await registry.register(GitHubCodebase(db=state.db))
```

### Step 4: Add config

In `.env.example`:

```env
GITHUB_TOKEN=ghp_...   # GitHub personal access token (for creating PRs)
```

### Step 5: Create a specialist agent

Create `data/agents/github-reviewer.md`:

```markdown
# Agent: GitHub Reviewer
A specialist agent for reviewing GitHub codebases, finding bugs, and creating patches.

## Capabilities
- code_review
- debugging
- security

## System Prompt
You are a senior code reviewer. When given a repository, you:
1. Index the codebase into memory
2. Search for the relevant code sections
3. Analyze for bugs, security issues, or improvements
4. Generate patches using unified diff format
5. Create pull requests with clear descriptions

Always explain your reasoning before generating patches.

## Preferred Model
qwen3:14b

## Preferred Backend
ollama

## Tools
- github_index_repo
- github_search_code
- github_read_file
- github_create_patch
- github_create_pr
- search_memory
- remember
```

### Step 6: Test it

```bash
# Start klaus
uv run klaus-dev

# In the chat, try:
# "Index the hybridx/klaus repo and find any potential security issues"
# "Search for how authentication is handled in the klaus codebase"
# "Create a patch to add input validation to the chat endpoint"
```

---

## Example Prompts for Contributors

These prompts describe real-world superpowers that can be built following the same pattern. Use them as starting points.

### Jira Integration

> **Build a Jira superpower** that:
> 1. Connects to a Jira instance using the REST API (`JIRA_URL`, `JIRA_TOKEN` env vars)
> 2. Provides tools: `jira_get_issue`, `jira_search`, `jira_create_issue`, `jira_update_status`
> 3. Stores issue context in memory at `/knowledge/jira/{project}/{issue_key}`
> 4. Create an MD agent `data/agents/project-manager.md` with capabilities `[planning, jira, project_management]`
> 5. The orchestrator should be able to: read a Jira ticket → create a plan → get human approval → generate code changes → create a PR
>
> **Files to create:**
> - `src/klaus/superpowers/builtin/jira_integration.py`
> - `data/agents/project-manager.md`
>
> **Files to modify:**
> - `src/klaus/app.py` (register the superpower)
> - `.env.example` (add `JIRA_URL`, `JIRA_TOKEN`)

### Code Execution Sandbox

> **Build a code execution superpower** that:
> 1. Spins up an isolated Podman container for code execution
> 2. Provides tools: `execute_code(language, code)`, `execute_tests(repo, test_cmd)`
> 3. Supports Python, JavaScript, and shell scripts
> 4. Returns stdout, stderr, and exit code
> 5. Auto-cleans containers after execution (30s timeout)
> 6. Stores execution results in memory for the reflect phase
>
> **Files to create:**
> - `src/klaus/superpowers/builtin/code_sandbox.py`
> - `data/agents/test-runner.md`
>
> **Design considerations:**
> - Use `podman run --rm --timeout=30` for isolation
> - Mount a temp directory for file I/O
> - Never run as root inside the container

### Slack Integration

> **Build a Slack superpower** that:
> 1. Connects via Slack Bot Token (`SLACK_BOT_TOKEN`)
> 2. Provides tools: `slack_send_message`, `slack_read_channel`, `slack_search`
> 3. Stores channel context in memory at `/knowledge/slack/{channel}`
> 4. The agent can summarize threads, answer questions about Slack history, and post updates
>
> **Files to create:**
> - `src/klaus/superpowers/builtin/slack_integration.py`

### GitLab MR Automation

> **Build a GitLab superpower** that:
> 1. Connects to GitLab via REST API (`GITLAB_URL`, `GITLAB_TOKEN`)
> 2. Indexes a project's codebase into vector embeddings
> 3. Reads Jira/GitLab issues to understand what needs to change
> 4. Generates code patches and creates merge requests
> 5. Responds to MR review comments and pushes fixes
>
> **The full workflow:**
> ```
> Read Issue → Index Codebase → Plan Changes → Human Approval
> → Generate Patches → Create MR → Wait for Review → Address Feedback
> ```
>
> **Files to create:**
> - `src/klaus/superpowers/builtin/gitlab_integration.py`
> - `data/agents/gitlab-developer.md`

---

## Adding an MCP Server

The simplest way to give klaus new tools is via MCP (Model Context Protocol). No Python code needed.

### Option A: Auto-discovery (config file)

Add to `mcp.json` in the project root:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..." }
    }
  }
}
```

### Option B: Runtime API

```bash
curl -X POST http://localhost:8000/api/mcp/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "github",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..."}
  }'
```

### Option C: URL-based (SSE/HTTP) with auth

```bash
curl -X POST http://localhost:8000/api/mcp/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "atlassian",
    "url": "https://mcp.atlassian.com/v1/sse",
    "headers": {"Authorization": "Bearer your-token-here"}
  }'
```

Or use the Settings → MCP Servers page in the UI, which provides a visual form for both command-based and URL-based servers.

---

## Architecture of a Superpower

Every superpower follows this lifecycle:

```
Registration → Memory Binding → Activation → Tool Collection → Use → Deactivation
     │              │                │              │            │
     ▼              ▼                ▼              ▼            ▼
app.py calls   Registry binds   activate()    get_tools()   LangGraph
register()     memory manager   runs setup    returns tools  invokes them
```

### The base class

```python
class Superpower(ABC):
    # Required
    name: str               # Unique ID → /superpowers/{name}
    description: str        # Shown in UI dashboard
    get_tools() -> list     # LangChain tools for the agent

    # Optional
    version: str = "0.1.0"
    tags: list[str] = []
    activate() -> None      # Async setup (API clients, DB connections)
    deactivate() -> None    # Async cleanup

    # Built-in helpers
    remember(key, content)  # Write to /superpowers/{name}/{key}
    recall(key) -> str      # Read from /superpowers/{name}/{key}
```

### Patterns

**External API client:**
```python
async def activate(self) -> None:
    await super().activate()
    self._http = httpx.AsyncClient(
        base_url="https://api.example.com",
        headers={"Authorization": f"Bearer {os.getenv('API_TOKEN')}"},
    )
```

**Database access:**
```python
def __init__(self, db=None):
    super().__init__()
    self._db = db
```

**Indexing content into vector memory:**
```python
if self._memory:
    self._memory.put(f"/knowledge/my_data/{key}", content, tags=["my_tag"])
    await self._memory.flush_embeddings()
```

---

## Checklist for New Features

When adding any extension to klaus:

- [ ] Create the implementation (MD file or Python class)
- [ ] Register in `app.py` if it's a Python superpower
- [ ] Add environment variables to `.env.example`
- [ ] Write tests in `tests/`
- [ ] Update `docs/guide/adding-tools.md` or `docs/guide/extending-klaus.md`
- [ ] Update `README.md` project structure and relevant sections
- [ ] Update `CONTRIBUTING.md` if the setup process changes
- [ ] Update `docs/ARCHITECTURE.md` if it changes the system architecture
