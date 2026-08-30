"""Knowledge System Module.

Asynchronous semantic knowledge layer for Obsidian integration, trade journaling,
temporal RAG search, and Learning Loop V2 lifecycle management.
"""

from knowledge.api import KnowledgeAPI
from knowledge.indexing.index import KnowledgeIndex
from knowledge.indexing.worker import KnowledgeQueue, KnowledgeSyncWorker
from knowledge.learning.pipeline import LearningPipeline
from knowledge.models import (
    CandidateLesson,
    KnowledgeNote,
    LearningStage,
    NoteCategory,
    TradeJournalEntry,
)
from knowledge.obsidian.journal import TradeJournalManager
from knowledge.obsidian.parser import MarkdownParser
from knowledge.obsidian.vault import ObsidianVaultManager
from knowledge.search.engine import SearchEngine

__all__ = [
    "CandidateLesson",
    "KnowledgeAPI",
    "KnowledgeIndex",
    "KnowledgeNote",
    "KnowledgeQueue",
    "KnowledgeSyncWorker",
    "LearningPipeline",
    "LearningStage",
    "MarkdownParser",
    "NoteCategory",
    "ObsidianVaultManager",
    "SearchEngine",
    "TradeJournalEntry",
    "TradeJournalManager",
]
