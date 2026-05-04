"""Memory tree endpoints — browse, search, read/write."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from klaus.api.deps import get_state

router = APIRouter(prefix="/memory", tags=["memory"])


class PutRequest(BaseModel):
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    merge: bool = False


@router.get("/tree")
async def tree_overview():
    """High-level tree structure."""
    state = get_state()
    tree = state.memory.tree

    def _summary(node, depth=0, max_depth=3):
        if depth > max_depth:
            return {"name": node.name, "children": f"({node.child_count} more)"}
        return {
            "name": node.name,
            "has_content": bool(node.content),
            "children": {
                k: _summary(v, depth + 1, max_depth)
                for k, v in node.children.items()
            },
        }

    return {"tree": _summary(tree.root), "total_nodes": tree.size}


@router.get("/ls")
async def ls(path: str = "/"):
    state = get_state()
    return {"path": path, "children": state.memory.ls(path)}


@router.get("/get")
async def get_node(path: str):
    state = get_state()
    node = state.memory.get(path)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {path}")
    return {
        "path": path,
        "name": node.name,
        "content": node.content,
        "metadata": node.metadata,
        "tags": node.tags,
        "children": list(node.children.keys()),
        "created_at": node.created_at,
        "updated_at": node.updated_at,
        "access_count": node.access_count,
    }


@router.post("/put")
async def put_node(path: str, req: PutRequest):
    state = get_state()
    state.memory.put(
        path,
        content=req.content,
        metadata=req.metadata if req.metadata else None,
        tags=req.tags if req.tags else None,
        merge=req.merge,
    )
    return {"path": path, "status": "ok"}


@router.delete("/delete")
async def delete_node(path: str):
    state = get_state()
    deleted = state.memory.delete(path)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Node not found: {path}")
    return {"path": path, "status": "deleted"}


@router.get("/graph")
async def memory_graph():
    """Return the memory tree as a flat node list optimized for graph rendering."""
    state = get_state()
    tree = state.memory.tree
    nodes: list[dict] = []

    def _flatten(node, path: str, parent_id: str | None):
        branch = path.strip("/").split("/")[0] if path.strip("/") else "root"
        nodes.append({
            "id": node.id,
            "label": node.name or "root",
            "path": path or "/",
            "parent": parent_id,
            "content_preview": (
                (node.content[:120] + "...") if len(node.content) > 120 else node.content
            ),
            "tags": node.tags,
            "branch": branch,
            "children_count": len(node.children),
            "access_count": node.access_count,
        })
        for name, child in node.children.items():
            child_path = f"{path}/{name}" if path != "/" else f"/{name}"
            _flatten(child, child_path, node.id)

    _flatten(tree.root, "/", None)
    return {"nodes": nodes, "total": len(nodes)}


@router.get("/search")
async def search_memory(q: str, root: str = "/", max_results: int = 15):
    state = get_state()
    results = state.memory.search(q, root_path=root, max_results=max_results)
    return {
        "query": q,
        "results": [
            {
                "path": path,
                "content": node.content[:300],
                "score": round(score, 2),
                "tags": node.tags,
            }
            for path, node, score in results
        ],
    }
