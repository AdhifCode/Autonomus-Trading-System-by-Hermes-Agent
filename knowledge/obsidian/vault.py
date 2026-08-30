"""Obsidian Vault Directory & File System Manager.

Handles reading, writing, and scanning markdown notes in an Obsidian vault.
In accordance with architecture §16, Obsidian failure MUST NOT stop trading execution.
"""

from __future__ import annotations

from pathlib import Path

from core.logging import get_logger
from knowledge.models import KnowledgeNote, NoteCategory
from knowledge.obsidian.parser import MarkdownParser

logger = get_logger(__name__)


class ObsidianVaultManager:
    """Manager for interacting with the Obsidian vault filesystem."""

    def __init__(self, vault_path: str | Path = "~/obsidian-vault") -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.parser = MarkdownParser()

    def is_available(self) -> bool:
        """Check if the Obsidian vault path exists and is accessible."""
        try:
            return self.vault_path.exists() and self.vault_path.is_dir()
        except Exception as exc:
            logger.warning(f"Obsidian vault access check failed: {exc}")
            return False

    def ensure_vault_structure(self) -> bool:
        """Create standard Obsidian directory structure if available."""
        if not self.is_available():
            try:
                self.vault_path.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                logger.warning(
                    f"Could not create Obsidian vault root directory ({self.vault_path}): {exc}"
                )
                return False

        try:
            for category in NoteCategory:
                cat_dir = self.vault_path / category.value
                cat_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as exc:
            logger.warning(f"Failed to create Obsidian subdirectories: {exc}")
            return False

    def scan_vault(self) -> list[KnowledgeNote]:
        """Scan all markdown files in the Obsidian vault and parse them into KnowledgeNote objects.

        Returns empty list if vault is unavailable (non-blocking).
        """
        if not self.is_available():
            logger.info(f"Obsidian vault unavailable at {self.vault_path}, skipping vault scan")
            return []

        notes: list[KnowledgeNote] = []
        try:
            for md_file in self.vault_path.rglob("*.md"):
                try:
                    rel_path = str(md_file.relative_to(self.vault_path))
                    content = md_file.read_text(encoding="utf-8")
                    note = self.parser.parse(content, file_path=rel_path)
                    notes.append(note)
                except Exception as file_err:
                    logger.warning(f"Failed to parse Obsidian file {md_file}: {file_err}")
        except Exception as err:
            logger.warning(f"Error scanning Obsidian vault directory: {err}")

        return notes

    def read_note(self, relative_path: str) -> KnowledgeNote | None:
        """Read a single markdown note relative to the vault root."""
        if not self.is_available():
            return None

        file_path = self.vault_path / relative_path
        if not file_path.exists():
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
            return self.parser.parse(content, file_path=relative_path)
        except Exception as exc:
            logger.warning(f"Failed to read note {relative_path}: {exc}")
            return None

    def write_note(self, category: NoteCategory, filename: str, content: str) -> bool:
        """Write a markdown note into the specified vault category directory.

        Returns True on success, False if write fails or vault is unavailable.
        Does NOT raise exceptions to guarantee caller execution safety.
        """
        try:
            self.ensure_vault_structure()
            cat_dir = self.vault_path / category.value
            cat_dir.mkdir(parents=True, exist_ok=True)

            if not filename.endswith(".md"):
                filename = f"{filename}.md"

            file_path = cat_dir / filename
            file_path.write_text(content, encoding="utf-8")
            logger.info(f"Saved note to Obsidian vault: {category.value}/{filename}")
            return True
        except Exception as exc:
            logger.warning(
                f"Failed to write note to Obsidian vault ({category.value}/{filename}): {exc}"
            )
            return False
