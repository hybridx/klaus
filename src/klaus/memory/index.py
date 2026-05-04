"""Memory index — semantic and keyword search over the tree.

Provides smarter retrieval than raw tree.search() by combining:
1. Keyword matching (fast, exact)
2. Tag filtering
3. Recency weighting
4. Optional embedding-based semantic search (when an embedding model is available)

The index doesn't store data — it queries the tree and ranks results.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

from klaus.memory.tree import MemoryNode, MemoryTree

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    path: str
    node: MemoryNode
    score: float
    match_reason: str


class MemoryIndex:
    """Search and retrieval engine for the memory tree."""

    RECENCY_HALF_LIFE = 3600.0  # 1 hour — recent nodes score higher

    def __init__(self, tree: MemoryTree) -> None:
        self._tree = tree

    def search(
        self,
        query: str,
        root_path: str = "/",
        tags: list[str] | None = None,
        max_results: int = 15,
    ) -> list[SearchResult]:
        """Combined keyword + tag + recency search."""
        terms = query.lower().split()
        now = time.time()
        results: list[SearchResult] = []

        for path, node in self._tree.walk(root_path):
            score = 0.0
            reasons: list[str] = []

            # Keyword match
            searchable = f"{node.name} {node.content} {' '.join(node.tags)}".lower()
            keyword_score = sum(searchable.count(t) for t in terms)
            if keyword_score > 0:
                name_bonus = sum(2.0 for t in terms if t in node.name.lower())
                keyword_score += name_bonus
                score += keyword_score
                reasons.append("keyword")

            # Tag filter
            if tags:
                tag_match = len(set(tags) & set(node.tags))
                if tag_match:
                    score += tag_match * 3.0
                    reasons.append("tag")

            if score == 0:
                continue

            # Recency boost (exponential decay)
            age = now - node.updated_at
            recency = math.exp(-age / self.RECENCY_HALF_LIFE)
            score *= 1.0 + recency

            # Access frequency boost (popular nodes are likely relevant)
            if node.access_count > 0:
                score *= 1.0 + math.log1p(node.access_count) * 0.1

            results.append(SearchResult(
                path=path,
                node=node,
                score=score,
                match_reason="+".join(reasons),
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results]

    def gather_context(
        self,
        query: str,
        conversation_path: str | None = None,
        max_tokens_estimate: int = 2000,
    ) -> str:
        """Build a memory context string for injection into the agent.

        Searches the tree, collects relevant nodes, and formats them
        into a concise text block that fits within a token budget.
        """
        parts: list[str] = []
        char_budget = max_tokens_estimate * 4  # rough chars-per-token

        # 1. Conversation-specific context (if we know the conversation branch)
        if conversation_path:
            conv_nodes = self._tree.context_for(conversation_path)
            for node in conv_nodes[:5]:
                if node.content:
                    parts.append(f"[{node.name}] {node.content}")

        # 2. Search knowledge for relevant facts
        knowledge_hits = self.search(query, root_path="/knowledge", max_results=5)
        for hit in knowledge_hits:
            if hit.node.content:
                parts.append(f"[memory:{hit.path}] {hit.node.content}")

        # 3. Active superpowers (so the agent knows its capabilities)
        sp_node = self._tree.get("/superpowers")
        if sp_node:
            sp_names = [
                f"{name}: {child.content}"
                for name, child in sp_node.children.items()
                if child.content
            ]
            if sp_names:
                parts.append("[capabilities] " + "; ".join(sp_names))

        # Trim to budget
        text = "\n".join(parts)
        if len(text) > char_budget:
            text = text[:char_budget] + "\n[...truncated]"

        return text
