"""Asynchronous Knowledge Sync Worker & Queuing System.

Manages background indexing and queued vault operations.
Guarantees Obsidian vault failures DO NOT block execution.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from knowledge.indexing.index import KnowledgeIndex
from knowledge.models import NoteCategory
from knowledge.obsidian.vault import ObsidianVaultManager

logger = get_logger(__name__)


class KnowledgeQueue:
    """In-memory processing queue for deferred knowledge notes and sync events."""

    def __init__(self) -> None:
        self._queue: list[dict[str, Any]] = []

    def enqueue(self, task_type: str, data: dict[str, Any]) -> None:
        """Enqueue a pending knowledge task."""
        self._queue.append({"task_type": task_type, "data": data})

    def pop_all(self) -> list[dict[str, Any]]:
        """Drain and return all queued tasks."""
        items = list(self._queue)
        self._queue.clear()
        return items

    @property
    def size(self) -> int:
        """Return count of queued pending tasks."""
        return len(self._queue)


class KnowledgeSyncWorker:
    """Sync worker that indexes Obsidian vault notes and processes deferred queue items."""

    def __init__(
        self,
        index: KnowledgeIndex | None = None,
        vault_manager: ObsidianVaultManager | None = None,
    ) -> None:
        self.index = index or KnowledgeIndex()
        self.vault = vault_manager or ObsidianVaultManager()
        self.queue = KnowledgeQueue()

    def sync(self) -> int:
        """Scan Obsidian vault, update index, build link graph, and process queued tasks.

        Returns the total number of notes currently indexed.
        """
        # 1. Process queued tasks if vault is available
        if self.vault.is_available() and self.queue.size > 0:
            tasks = self.queue.pop_all()
            for task in tasks:
                t_type = task.get("task_type")
                t_data = task.get("data", {})
                if t_type == "write_note":
                    category = t_data.get("category")
                    filename = t_data.get("filename")
                    content = t_data.get("content")
                    if category and filename and content:
                        self.vault.write_note(category, filename, content)

        # 2. Scan vault notes (returns empty list safely if vault is unavailable)
        notes = self.vault.scan_vault()

        # 3. Update index
        self.index.clear()
        for note in notes:
            self.index.add_note(note)

        # 4. Compute link graph
        self.index.build_link_graph()

        logger.info(f"Knowledge sync complete. Total notes indexed: {len(notes)}")
        return len(notes)

    def queue_note_write(self, category_value: str, filename: str, content: str) -> None:
        """Queue a note write operation if vault is currently unavailable."""
        if self.vault.is_available():
            self.vault.write_note(NoteCategory(category_value), filename, content)
        else:
            logger.info(f"Obsidian vault unavailable. Queuing note write for: {filename}")
            self.queue.enqueue(
                "write_note",
                {
                    "category": NoteCategory(category_value),
                    "filename": filename,
                    "content": content,
                },
            )
