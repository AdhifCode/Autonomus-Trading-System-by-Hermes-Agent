"""In-Memory & SQLite Backed Knowledge Index.

Maintains note metadata, tag indices, internal link graphs (wiki-links & backlinks),
and temporal provenance indexing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.logging import get_logger
from knowledge.models import KnowledgeNote, NoteCategory

logger = get_logger(__name__)


class KnowledgeIndex:
    """Index for managing knowledge notes, tag indices, and link graph relationships."""

    def __init__(self) -> None:
        self._notes: dict[str, KnowledgeNote] = {}  # key: note.path or note.note_id
        self._tag_index: dict[str, set[str]] = {}  # tag -> set of note keys
        self._category_index: dict[NoteCategory, set[str]] = {}  # category -> set of note keys
        self._title_lookup: dict[str, str] = {}  # lower title -> note key

    def clear(self) -> None:
        """Clear all indexed notes and indices."""
        self._notes.clear()
        self._tag_index.clear()
        self._category_index.clear()
        self._title_lookup.clear()

    def add_note(self, note: KnowledgeNote) -> None:
        """Add or update a KnowledgeNote in the index."""
        key = note.path or note.note_id
        self._notes[key] = note
        self._title_lookup[note.title.lower()] = key

        # Index tags
        for tag in note.tags:
            tag_clean = tag.lower().lstrip("#")
            if tag_clean not in self._tag_index:
                self._tag_index[tag_clean] = set()
            self._tag_index[tag_clean].add(key)

        # Index category
        if note.category not in self._category_index:
            self._category_index[note.category] = set()
        self._category_index[note.category].add(key)

    def build_link_graph(self) -> None:
        """Compute backlinks across all indexed notes based on internal [[wiki-links]]."""
        # Clear existing backlinks
        for note in self._notes.values():
            note.backlinks.clear()

        # Build reverse link graph
        for source_key, source_note in self._notes.items():
            for target_ref in source_note.internal_links:
                target_key = self._resolve_ref_to_key(target_ref)
                if target_key and target_key in self._notes:
                    target_note = self._notes[target_key]
                    if source_key not in target_note.backlinks:
                        target_note.backlinks.append(source_key)

    def _resolve_ref_to_key(self, ref: str) -> str | None:
        """Resolve a [[wiki-link]] target reference to an indexed note key."""
        # Exact match
        if ref in self._notes:
            return ref

        # Match by title (case-insensitive)
        ref_lower = ref.lower()
        if ref_lower in self._title_lookup:
            return self._title_lookup[ref_lower]

        # Partial path match
        for key in self._notes:
            if key.endswith(ref) or key.endswith(f"{ref}.md"):
                return key

        return None

    def get_note(self, key_or_path: str) -> KnowledgeNote | None:
        """Get note by exact key, path, or resolved title."""
        if key_or_path in self._notes:
            return self._notes[key_or_path]

        resolved_key = self._resolve_ref_to_key(key_or_path)
        if resolved_key and resolved_key in self._notes:
            return self._notes[resolved_key]

        return None

    def get_notes_by_tag(self, tag: str) -> list[KnowledgeNote]:
        """Get all notes matching a tag."""
        tag_clean = tag.lower().lstrip("#")
        keys = self._tag_index.get(tag_clean, set())
        return [self._notes[k] for k in keys if k in self._notes]

    def get_notes_by_category(self, category: NoteCategory) -> list[KnowledgeNote]:
        """Get all notes matching a category."""
        keys = self._category_index.get(category, set())
        return [self._notes[k] for k in keys if k in self._notes]

    def list_all_notes(
        self,
        as_of: datetime | None = None,
    ) -> list[KnowledgeNote]:
        """List all notes in the index.

        If `as_of` timestamp is provided, strictly filters out any notes where
        `available_at > as_of` to prevent temporal data leakage.
        """
        eval_time = as_of or datetime.now(UTC)
        results: list[KnowledgeNote] = []

        for note in self._notes.values():
            if note.available_at <= eval_time:
                results.append(note)

        return results

    def get_backlinks(self, key_or_path: str) -> list[KnowledgeNote]:
        """Get all notes that link to the specified note."""
        note = self.get_note(key_or_path)
        if not note:
            return []

        backlink_notes: list[KnowledgeNote] = []
        for bl_key in note.backlinks:
            bl_note = self.get_note(bl_key)
            if bl_note:
                backlink_notes.append(bl_note)
        return backlink_notes
