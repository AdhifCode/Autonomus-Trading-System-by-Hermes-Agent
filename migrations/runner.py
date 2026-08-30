"""Database migration framework.

Runs numbered SQL migration files in order, tracking applied versions
in a `schema_migrations` table. Forward-only for safety.

Migration files are named: 001_description.sql, 002_description.sql, etc.
"""

from __future__ import annotations

import re
from pathlib import Path

from adapters.database.sqlite import SQLiteManager
from core.errors import MigrationError
from core.logging import get_logger

logger = get_logger(__name__)

# Pattern: 001_description.sql
_MIGRATION_PATTERN = re.compile(r"^(\d{3})_(.+)\.sql$")


class MigrationRunner:
    """Runs SQL migrations against a SQLite database.

    Migrations are applied in numeric order. Each migration is tracked
    in the `schema_migrations` table to prevent re-application.
    """

    def __init__(
        self,
        db: SQLiteManager,
        migrations_dir: str | Path = "migrations",
    ) -> None:
        self._db = db
        self._migrations_dir = Path(migrations_dir)

    def _ensure_migration_table(self) -> None:
        """Create the schema_migrations table if it doesn't exist."""
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._db.commit()

    def _get_applied_versions(self) -> set[int]:
        """Return the set of already-applied migration versions."""
        cursor = self._db.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cursor.fetchall()}

    def _discover_migrations(self) -> list[tuple[int, str, Path]]:
        """Discover migration files sorted by version number.

        Returns:
            List of (version, name, path) tuples sorted by version.

        Raises:
            MigrationError: If migration directory doesn't exist.
        """
        if not self._migrations_dir.exists():
            raise MigrationError(f"Migrations directory not found: {self._migrations_dir}")

        migrations: list[tuple[int, str, Path]] = []

        for filepath in sorted(self._migrations_dir.iterdir()):
            if not filepath.is_file():
                continue
            match = _MIGRATION_PATTERN.match(filepath.name)
            if match:
                version = int(match.group(1))
                name = match.group(2)
                migrations.append((version, name, filepath))

        return migrations

    def get_current_version(self) -> int:
        """Return the highest applied migration version, or 0 if none."""
        self._ensure_migration_table()
        applied = self._get_applied_versions()
        return max(applied) if applied else 0

    def get_pending_migrations(self) -> list[tuple[int, str, Path]]:
        """Return migrations that have not yet been applied."""
        self._ensure_migration_table()
        applied = self._get_applied_versions()
        all_migrations = self._discover_migrations()
        return [(v, n, p) for v, n, p in all_migrations if v not in applied]

    def run(self) -> int:
        """Apply all pending migrations.

        Returns:
            Number of migrations applied.

        Raises:
            MigrationError: If a migration file cannot be read or executed.
        """
        self._ensure_migration_table()
        pending = self.get_pending_migrations()

        if not pending:
            logger.info("No pending migrations")
            return 0

        applied_count = 0
        for version, name, filepath in pending:
            logger.info(
                f"Applying migration {version:03d}_{name}",
                extra={"metadata": {"version": version, "name": name}},
            )
            try:
                sql = filepath.read_text(encoding="utf-8")
                self._db.executescript(sql)
                self._db.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    (version, name),
                )
                self._db.commit()
                applied_count += 1
                logger.info(
                    f"Migration {version:03d}_{name} applied successfully",
                    extra={"metadata": {"version": version, "name": name}},
                )
            except Exception as e:
                self._db.rollback()
                raise MigrationError(f"Migration {version:03d}_{name} failed: {e}") from e

        logger.info(
            f"Applied {applied_count} migration(s)",
            extra={"metadata": {"count": applied_count}},
        )
        return applied_count
