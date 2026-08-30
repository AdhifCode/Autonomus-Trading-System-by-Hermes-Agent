"""Full-Text, Tag, Link-Graph, and Temporal Provenance Search Engine.

Implements knowledge retrieval with strict temporal provenance filtering
and semantic search interface.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Protocol

from core.logging import get_logger
from knowledge.indexing.index import KnowledgeIndex
from knowledge.models import KnowledgeNote, NoteCategory

logger = get_logger(__name__)


class SemanticSearchProvider(Protocol):
    """Protocol interface for pluggable vector/semantic search engines."""

    def search_semantic(
        self,
        query: str,
        notes: list[KnowledgeNote],
        top_k: int = 10,
    ) -> list[tuple[KnowledgeNote, float]]:
        """Search notes semantically and return list of (note, relevance_score)."""
        ...


class DefaultTFIDFSearchProvider:
    """Fallback term-frequency search provider for semantic similarity estimation."""

    def search_semantic(
        self,
        query: str,
        notes: list[KnowledgeNote],
        top_k: int = 10,
    ) -> list[tuple[KnowledgeNote, float]]:
        """Compute basic keyword overlap relevance score."""
        words = set(re.findall(r"\w+", query.lower()))
        if not words:
            return [(n, 0.0) for n in notes[:top_k]]

        scored: list[tuple[KnowledgeNote, float]] = []
        for note in notes:
            text = f"{note.title} {' '.join(note.tags)} {note.content}".lower()
            text_words = set(re.findall(r"\w+", text))
            overlap = len(words.intersection(text_words))
            score = overlap / len(words) if words else 0.0
            if score > 0:
                scored.append((note, round(score, 4)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


class SearchEngine:
    """Unified Search Engine for the Knowledge System."""

    def __init__(
        self,
        index: KnowledgeIndex,
        semantic_provider: SemanticSearchProvider | None = None,
    ) -> None:
        self.index = index
        self.semantic_provider = semantic_provider or DefaultTFIDFSearchProvider()

    def search(
        self,
        query: str = "",
        tags: list[str] | None = None,
        category: NoteCategory | str | None = None,
        as_of: datetime | None = None,
        limit: int = 20,
    ) -> list[KnowledgeNote]:
        """Perform full-text & tag search with temporal provenance boundary enforcement.

        CRITICAL: If `as_of` is provided, any note where `available_at > as_of` is strictly
        excluded to prevent temporal look-ahead bias and data leakage (architecture §26).
        """
        eval_time = as_of or datetime.now(UTC)

        # 1. Fetch notes respecting temporal provenance
        candidate_notes = self.index.list_all_notes(as_of=eval_time)

        # 2. Filter by category if provided
        if category:
            cat_val = category.value if isinstance(category, NoteCategory) else str(category)
            candidate_notes = [
                n for n in candidate_notes if n.category.value.lower() == cat_val.lower()
            ]

        # 3. Filter by tags if provided
        if tags:
            tag_set = {t.lower().lstrip("#") for t in tags}
            candidate_notes = [
                n for n in candidate_notes if tag_set.issubset({t.lower() for t in n.tags})
            ]

        # 4. Filter/score by query text if provided
        if query and query.strip():
            query_terms = [q.lower() for q in query.split()]
            scored_results: list[tuple[KnowledgeNote, float]] = []

            for note in candidate_notes:
                score = 0.0
                title_lower = note.title.lower()
                content_lower = note.content.lower()

                for term in query_terms:
                    if term in title_lower:
                        score += 5.0
                    if any(term in tag.lower() for tag in note.tags):
                        score += 3.0
                    if term in content_lower:
                        score += 1.0

                if score > 0:
                    scored_results.append((note, score))

            scored_results.sort(key=lambda x: x[1], reverse=True)
            return [item[0] for item in scored_results[:limit]]

        return candidate_notes[:limit]

    def search_semantic(
        self,
        query: str,
        as_of: datetime | None = None,
        limit: int = 10,
    ) -> list[tuple[KnowledgeNote, float]]:
        """Search semantically with temporal provenance enforcement."""
        eval_time = as_of or datetime.now(UTC)
        candidate_notes = self.index.list_all_notes(as_of=eval_time)
        return self.semantic_provider.search_semantic(query, candidate_notes, top_k=limit)
