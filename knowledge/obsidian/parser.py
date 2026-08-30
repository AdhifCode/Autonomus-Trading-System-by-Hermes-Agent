"""Markdown & YAML Frontmatter Parser for Obsidian Notes.

Parses markdown files, extracting:
- YAML frontmatter metadata
- [[Internal Links]] (and [[Link|Alias]] syntax)
- #tags and YAML tags
- Provenance metadata (created_at, available_at, author, confidence, source_trade_id)
- Title & sections
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import yaml

from knowledge.models import KnowledgeNote, NoteCategory


class MarkdownParser:
    """Parser for Obsidian Markdown notes."""

    # Regex patterns for parsing
    _FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
    _WIKILINK_PATTERN = re.compile(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]")
    _INLINE_TAG_PATTERN = re.compile(r"(?:^|\s)#([a-zA-Z0-9_\-\/]+)")
    _HEADING_PATTERN = re.compile(r"^#+\s+(.+)$", re.MULTILINE)

    def parse(self, raw_content: str, file_path: str = "") -> KnowledgeNote:
        """Parse raw markdown content into a KnowledgeNote domain object."""
        frontmatter: dict[str, Any] = {}
        content_body = raw_content

        match = self._FRONTMATTER_PATTERN.match(raw_content)
        if match:
            yaml_str = match.group(1)
            content_body = match.group(2)
            try:
                parsed_yaml = yaml.safe_load(yaml_str)
                if isinstance(parsed_yaml, dict):
                    frontmatter = parsed_yaml
            except Exception:
                frontmatter = {}

        # 1. Extract internal wiki-links [[Target Note]]
        internal_links = list(dict.fromkeys(self._WIKILINK_PATTERN.findall(content_body)))

        # 2. Extract tags (combine YAML frontmatter tags + inline #tags)
        tags_set: set[str] = set()
        if "tags" in frontmatter:
            raw_tags = frontmatter["tags"]
            if isinstance(raw_tags, list):
                for t in raw_tags:
                    tags_set.add(str(t).lstrip("#"))
            elif isinstance(raw_tags, str):
                tags_set.add(raw_tags.lstrip("#"))

        inline_tags = self._INLINE_TAG_PATTERN.findall(content_body)
        for it in inline_tags:
            tags_set.add(it)

        # 3. Determine title (from frontmatter title -> first # Heading -> file basename)
        title = frontmatter.get("title")
        if not title:
            heading_match = self._HEADING_PATTERN.search(content_body)
            if heading_match:
                title = heading_match.group(1).strip()
            elif file_path:
                basename = file_path.rsplit("/", 1)[-1]
                title = basename.removesuffix(".md")
            else:
                title = "Untitled Note"

        # 4. Determine category from frontmatter or path prefix
        category = NoteCategory.REFERENCES
        cat_str = frontmatter.get("category")
        if cat_str:
            for member in NoteCategory:
                if member.value.lower() == str(cat_str).lower():
                    category = member
                    break
        elif file_path:
            for member in NoteCategory:
                if member.value in file_path:
                    category = member
                    break

        # 5. Extract provenance metadata
        created_at = self._parse_datetime(frontmatter.get("created_at"))
        available_at = self._parse_datetime(frontmatter.get("available_at")) or created_at
        author = str(frontmatter.get("author", "System"))

        confidence: float | None = None
        if "confidence" in frontmatter and frontmatter["confidence"] is not None:
            try:
                confidence = float(frontmatter["confidence"])
            except (ValueError, TypeError):
                confidence = None

        source_trade_id = frontmatter.get("source_trade_id")
        if source_trade_id:
            source_trade_id = str(source_trade_id)

        source_event_id = frontmatter.get("source_event_id")
        if source_event_id:
            source_event_id = str(source_event_id)

        note_id = file_path or f"NOTE-{title.replace(' ', '-').upper()}"

        return KnowledgeNote(
            note_id=note_id,
            path=file_path or note_id,
            title=title,
            category=category,
            content=content_body.strip(),
            yaml_frontmatter=frontmatter,
            tags=sorted(tags_set),
            internal_links=internal_links,
            backlinks=[],
            created_at=created_at,
            available_at=available_at,
            author=author,
            confidence=confidence,
            source_trade_id=source_trade_id,
            source_event_id=source_event_id,
        )

    def _parse_datetime(self, val: Any) -> datetime:
        """Parse datetime string or return current UTC time."""
        if isinstance(val, datetime):
            return val if val.tzinfo else val.replace(tzinfo=UTC)
        if isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val)
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except ValueError:
                pass
        return datetime.now(UTC)
