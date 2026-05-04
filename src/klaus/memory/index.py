"""Memory index — semantic and keyword search over the tree.

Provides smarter retrieval than raw tree.search() by combining:
1. Keyword matching (fast, exact)
2. Tag filtering
3. Recency weighting
4. Embedding-based semantic search via pgvector (when configured)

The index doesn't store data — it queries the tree and ranks results.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from klaus.memory.tree import MemoryNode, MemoryTree

if TYPE_CHECKING:
    from klaus.db import Database

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    path: str
    node: MemoryNode
    score: float
    match_reason: str


class EmbeddingModel:
    """Lazy-loaded sentence-transformers model for generating embeddings.

    Uses all-MiniLM-L6-v2 (384 dimensions, ~80MB, CPU-friendly).
    The model is loaded on first use and cached in memory.
    """

    _instance: EmbeddingModel | None = None
    _model = None

    def __init__(self) -> None:
        self._model = None

    @classmethod
    def get(cls) -> EmbeddingModel:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def encode(self, text: str) -> list[float]:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading embedding model (all-MiniLM-L6-v2)...")
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Embedding model ready")
            except ImportError:
                logger.warning(
                    "sentence-transformers not installed — "
                    "falling back to keyword search only"
                )
                return []
            except Exception as exc:
                logger.error("Failed to load embedding model: %s", exc)
                return []

        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            self.encode("")
            if self._model is None:
                return [[] for _ in texts]
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]


class MemoryIndex:
    """Search and retrieval engine for the memory tree."""

    RECENCY_HALF_LIFE = 3600.0

    def __init__(
        self,
        tree: MemoryTree,
        db: Database | None = None,
    ) -> None:
        self._tree = tree
        self._db = db
        self._embedder: EmbeddingModel | None = None

    def _get_embedder(self) -> EmbeddingModel:
        if self._embedder is None:
            self._embedder = EmbeddingModel.get()
        return self._embedder

    async def index_node(self, path: str, content: str) -> None:
        """Generate and store an embedding for a memory node."""
        if not self._db or not content.strip():
            return
        embedder = self._get_embedder()
        vec = embedder.encode(content[:2000])
        if vec:
            await self._db.save_embedding(path, content[:500], vec)

    async def index_tree(self, root_path: str = "/knowledge") -> int:
        """Batch-index all nodes under a path. Returns count of indexed nodes."""
        if not self._db:
            return 0

        embedder = self._get_embedder()
        paths: list[str] = []
        texts: list[str] = []

        for path, node in self._tree.walk(root_path):
            if node.content.strip():
                paths.append(path)
                texts.append(node.content[:2000])

        if not texts:
            return 0

        vectors = embedder.encode_batch(texts)
        count = 0
        for path, text, vec in zip(paths, texts, vectors, strict=True):
            if vec:
                await self._db.save_embedding(path, text[:500], vec)
                count += 1

        logger.info("Indexed %d nodes under %s", count, root_path)
        return count

    async def semantic_search(
        self, query: str, limit: int = 10
    ) -> list[SearchResult]:
        """Search memory using vector similarity via pgvector."""
        if not self._db:
            return []

        embedder = self._get_embedder()
        query_vec = embedder.encode(query)
        if not query_vec:
            return []

        hits = await self._db.search_embeddings(query_vec, limit=limit)
        results = []
        for hit in hits:
            node = self._tree.get(hit["path"])
            if node:
                results.append(SearchResult(
                    path=hit["path"],
                    node=node,
                    score=hit["similarity"],
                    match_reason="semantic",
                ))
        return results

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

            searchable = (
                f"{node.name} {node.content} {' '.join(node.tags)}".lower()
            )
            keyword_score = sum(searchable.count(t) for t in terms)
            if keyword_score > 0:
                name_bonus = sum(2.0 for t in terms if t in node.name.lower())
                keyword_score += name_bonus
                score += keyword_score
                reasons.append("keyword")

            if tags:
                tag_match = len(set(tags) & set(node.tags))
                if tag_match:
                    score += tag_match * 3.0
                    reasons.append("tag")

            if score == 0:
                continue

            age = now - node.updated_at
            recency = math.exp(-age / self.RECENCY_HALF_LIFE)
            score *= 1.0 + recency

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

    async def hybrid_search(
        self,
        query: str,
        root_path: str = "/",
        tags: list[str] | None = None,
        max_results: int = 15,
    ) -> list[SearchResult]:
        """Combined keyword + semantic search. Best of both worlds."""
        keyword_results = self.search(
            query, root_path=root_path, tags=tags, max_results=max_results
        )

        if not self._db:
            return keyword_results

        semantic_results = await self.semantic_search(query, limit=max_results)

        seen_paths: set[str] = set()
        merged: list[SearchResult] = []

        for r in keyword_results:
            seen_paths.add(r.path)
            sem_match = next(
                (s for s in semantic_results if s.path == r.path), None
            )
            if sem_match:
                r.score = r.score * 0.4 + sem_match.score * 10.0 * 0.6
                r.match_reason += "+semantic"
            merged.append(r)

        for r in semantic_results:
            if r.path not in seen_paths:
                r.score = r.score * 10.0
                merged.append(r)

        merged.sort(key=lambda r: r.score, reverse=True)
        return merged[:max_results]

    async def gather_context(
        self,
        query: str,
        conversation_path: str | None = None,
        max_tokens_estimate: int = 2000,
    ) -> str:
        """Build a memory context string for injection into the agent.

        Uses hybrid search (keyword + semantic) when embeddings are available.
        """
        parts: list[str] = []
        char_budget = max_tokens_estimate * 4

        if conversation_path:
            conv_nodes = self._tree.context_for(conversation_path)
            for node in conv_nodes[:5]:
                if node.content:
                    parts.append(f"[{node.name}] {node.content}")

        knowledge_hits = await self.hybrid_search(
            query, root_path="/knowledge", max_results=5
        )
        for hit in knowledge_hits:
            if hit.node.content:
                parts.append(
                    f"[memory:{hit.path}] {hit.node.content}"
                )

        sp_node = self._tree.get("/superpowers")
        if sp_node:
            sp_names = [
                f"{name}: {child.content}"
                for name, child in sp_node.children.items()
                if child.content
            ]
            if sp_names:
                parts.append("[capabilities] " + "; ".join(sp_names))

        text = "\n".join(parts)
        if len(text) > char_budget:
            text = text[:char_budget] + "\n[...truncated]"

        return text
