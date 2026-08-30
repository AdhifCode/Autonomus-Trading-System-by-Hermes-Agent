"""Unified Knowledge API System.

Serves as the master entrypoint for the Knowledge System:
- Sync & Indexing
- Search (Full-Text, Tags, Links, Temporal Provenance RAG)
- Trade Journaling
- Learning Pipeline V2 (Hypothesis -> Backtest -> Paper -> Human Approval -> Strategy)
- Resilient non-blocking vault interaction
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.logging import get_logger
from knowledge.indexing.index import KnowledgeIndex
from knowledge.indexing.worker import KnowledgeSyncWorker
from knowledge.learning.pipeline import LearningPipeline
from knowledge.models import (
    CandidateLesson,
    KnowledgeNote,
    LearningStage,
    NoteCategory,
    TradeJournalEntry,
)
from knowledge.obsidian.journal import TradeJournalManager
from knowledge.obsidian.vault import ObsidianVaultManager
from knowledge.search.engine import SearchEngine

logger = get_logger(__name__)


class KnowledgeAPI:
    """Master API interface for the Knowledge System."""

    def __init__(self, vault_path: str | Path = "~/obsidian-vault") -> None:
        self.vault_manager = ObsidianVaultManager(vault_path)
        self.index = KnowledgeIndex()
        self.sync_worker = KnowledgeSyncWorker(index=self.index, vault_manager=self.vault_manager)
        self.search_engine = SearchEngine(index=self.index)
        self.journal_manager = TradeJournalManager(vault_manager=self.vault_manager)
        self.learning_pipeline = LearningPipeline(vault_manager=self.vault_manager)

    # ---------------------------------------------------------------------------
    # Vault & Sync Operations
    # ---------------------------------------------------------------------------

    def is_vault_available(self) -> bool:
        """Check if Obsidian vault is currently accessible."""
        return self.vault_manager.is_available()

    def sync_knowledge(self) -> int:
        """Sync and re-index all notes from Obsidian vault.

        Returns total number of notes currently indexed.
        """
        return self.sync_worker.sync()

    # ---------------------------------------------------------------------------
    # Search & Retrieval
    # ---------------------------------------------------------------------------

    def search_notes(
        self,
        query: str = "",
        tags: list[str] | None = None,
        category: NoteCategory | str | None = None,
        as_of: datetime | None = None,
        limit: int = 20,
    ) -> list[KnowledgeNote]:
        """Search notes with strict temporal provenance enforcement (available_at <= as_of)."""
        return self.search_engine.search(
            query=query,
            tags=tags,
            category=category,
            as_of=as_of,
            limit=limit,
        )

    def search_semantic(
        self,
        query: str,
        as_of: datetime | None = None,
        limit: int = 10,
    ) -> list[tuple[KnowledgeNote, float]]:
        """Semantic search with temporal provenance enforcement."""
        return self.search_engine.search_semantic(query=query, as_of=as_of, limit=limit)

    def get_note(self, key_or_path: str) -> KnowledgeNote | None:
        """Get parsed KnowledgeNote by path or title reference."""
        return self.index.get_note(key_or_path)

    def get_backlinks(self, key_or_path: str) -> list[KnowledgeNote]:
        """Get all notes linking to the specified note."""
        return self.index.get_backlinks(key_or_path)

    # ---------------------------------------------------------------------------
    # Trade Journaling
    # ---------------------------------------------------------------------------

    def record_trade_journal_entry(self, entry: TradeJournalEntry) -> bool:
        """Record a structured trade log in Obsidian.

        If vault is unavailable, queues operation for later sync without stopping execution.
        """
        if self.is_vault_available():
            res = self.journal_manager.create_journal_note(entry)
            self.sync_knowledge()
            return res
        else:
            date_str = entry.timestamp_entry.strftime("%Y-%m-%d")
            filename = f"{date_str}_{entry.trade_id}_{entry.symbol}_{entry.direction}.md"
            content = self.journal_manager.format_entry_markdown(entry)
            self.sync_worker.queue_note_write(NoteCategory.TRADING_LOGS.value, filename, content)
            return False

    # ---------------------------------------------------------------------------
    # Learning Pipeline V2
    # ---------------------------------------------------------------------------

    def create_candidate_lesson(
        self,
        lesson_id: str,
        title: str,
        reflection_text: str,
        source_trade_id: str | None = None,
        target_strategy_id: str | None = None,
        author: str = "Hermes",
    ) -> CandidateLesson:
        """Create an LLM-reflected CandidateLesson (hypothesis only)."""
        lesson = self.learning_pipeline.create_candidate_lesson_from_reflection(
            lesson_id=lesson_id,
            title=title,
            reflection_text=reflection_text,
            source_trade_id=source_trade_id,
            target_strategy_id=target_strategy_id,
            author=author,
        )
        self.sync_knowledge()
        return lesson

    def advance_lesson_stage(
        self,
        lesson_id: str,
        target_stage: LearningStage,
        evidence_trade_ids: list[str] | None = None,
        human_approved: bool = False,
    ) -> CandidateLesson:
        """Advance lesson lifecycle stage."""
        lesson = self.learning_pipeline.advance_stage(
            lesson_id=lesson_id,
            target_stage=target_stage,
            evidence_trade_ids=evidence_trade_ids,
            human_approved=human_approved,
        )
        self.sync_knowledge()
        return lesson

    def get_lesson(self, lesson_id: str) -> CandidateLesson | None:
        """Get CandidateLesson by ID."""
        return self.learning_pipeline.get_lesson(lesson_id)
