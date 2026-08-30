"""Tests for migrations.runner — database migration framework."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.database.sqlite import SQLiteManager
from core.errors import MigrationError
from migrations.runner import MigrationRunner


class TestMigrationRunner:
    """Test migration discovery and execution."""

    def test_creates_migration_table(self, db: SQLiteManager, migrations_dir: Path):
        runner = MigrationRunner(db, migrations_dir)
        runner._ensure_migration_table()
        assert db.table_exists("schema_migrations")

    def test_discovers_migrations(self, db: SQLiteManager, migrations_dir: Path):
        runner = MigrationRunner(db, migrations_dir)
        migrations = runner._discover_migrations()
        assert len(migrations) == 2
        assert migrations[0][0] == 1  # version
        assert migrations[0][1] == "create_test_table"  # name
        assert migrations[1][0] == 2

    def test_ignores_non_migration_files(self, db: SQLiteManager, migrations_dir: Path):
        (migrations_dir / "README.md").write_text("ignore me")
        (migrations_dir / "helper.py").write_text("ignore me too")
        runner = MigrationRunner(db, migrations_dir)
        migrations = runner._discover_migrations()
        assert len(migrations) == 2  # only .sql files matching pattern

    def test_run_applies_all_pending(self, db: SQLiteManager, migrations_dir: Path):
        runner = MigrationRunner(db, migrations_dir)
        count = runner.run()
        assert count == 2
        assert db.table_exists("test_table")

    def test_run_is_idempotent(self, db: SQLiteManager, migrations_dir: Path):
        runner = MigrationRunner(db, migrations_dir)
        count1 = runner.run()
        count2 = runner.run()
        assert count1 == 2
        assert count2 == 0  # no pending migrations

    def test_get_current_version(self, db: SQLiteManager, migrations_dir: Path):
        runner = MigrationRunner(db, migrations_dir)
        assert runner.get_current_version() == 0
        runner.run()
        assert runner.get_current_version() == 2

    def test_get_pending_migrations(self, db: SQLiteManager, migrations_dir: Path):
        runner = MigrationRunner(db, migrations_dir)
        assert len(runner.get_pending_migrations()) == 2
        runner.run()
        assert len(runner.get_pending_migrations()) == 0

    def test_partial_application(self, db: SQLiteManager, migrations_dir: Path):
        """If only migration 1 was applied, migration 2 should be pending."""
        runner = MigrationRunner(db, migrations_dir)
        runner._ensure_migration_table()
        # Manually apply migration 1
        sql = (migrations_dir / "001_create_test_table.sql").read_text()
        db.executescript(sql)
        db.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (1, "create_test_table"),
        )
        db.commit()

        pending = runner.get_pending_migrations()
        assert len(pending) == 1
        assert pending[0][0] == 2

    def test_failed_migration_rolls_back(self, db: SQLiteManager, tmp_path: Path):
        mig_dir = tmp_path / "bad_migrations"
        mig_dir.mkdir()
        (mig_dir / "001_good.sql").write_text("CREATE TABLE good_table (id INTEGER PRIMARY KEY);")
        (mig_dir / "002_bad.sql").write_text("INVALID SQL STATEMENT;")

        runner = MigrationRunner(db, mig_dir)
        # First migration succeeds
        # Second migration should fail
        with pytest.raises(MigrationError, match="002_bad"):
            runner.run()

        # First migration should have been committed
        assert db.table_exists("good_table")
        # Version should be 1 (only first succeeded)
        assert runner.get_current_version() == 1

    def test_missing_migrations_dir(self, db: SQLiteManager):
        runner = MigrationRunner(db, "/nonexistent/path")
        with pytest.raises(MigrationError, match="not found"):
            runner.run()

    def test_empty_migrations_dir(self, db: SQLiteManager, tmp_path: Path):
        empty_dir = tmp_path / "empty_migrations"
        empty_dir.mkdir()
        runner = MigrationRunner(db, empty_dir)
        count = runner.run()
        assert count == 0

    def test_migration_version_tracking(self, db: SQLiteManager, migrations_dir: Path):
        runner = MigrationRunner(db, migrations_dir)
        runner.run()
        cursor = db.execute("SELECT version, name FROM schema_migrations ORDER BY version")
        rows = cursor.fetchall()
        assert len(rows) == 2
        assert rows[0]["version"] == 1
        assert rows[0]["name"] == "create_test_table"
        assert rows[1]["version"] == 2
        assert rows[1]["name"] == "add_column"
