"""Tests for adapters.database.sqlite — SQLite connection manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.database.sqlite import SQLiteManager
from core.errors import DatabaseError


class TestSQLiteManager:
    """Test SQLite connection manager."""

    def test_connect_creates_database(self, tmp_db_path: str):
        manager = SQLiteManager(tmp_db_path)
        conn = manager.connect()
        assert conn is not None
        assert Path(tmp_db_path).exists()
        manager.close()

    def test_connect_creates_parent_dirs(self, tmp_path: Path):
        db_path = str(tmp_path / "deep" / "nested" / "dir" / "test.db")
        manager = SQLiteManager(db_path)
        manager.connect()
        assert Path(db_path).exists()
        manager.close()

    def test_is_connected_property(self, tmp_db_path: str):
        manager = SQLiteManager(tmp_db_path)
        assert manager.is_connected is False
        manager.connect()
        assert manager.is_connected is True
        manager.close()
        assert manager.is_connected is False

    def test_double_connect_returns_same(self, tmp_db_path: str):
        manager = SQLiteManager(tmp_db_path)
        conn1 = manager.connect()
        conn2 = manager.connect()
        assert conn1 is conn2
        manager.close()

    def test_wal_mode_enabled(self, db: SQLiteManager):
        cursor = db.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_enabled(self, db: SQLiteManager):
        cursor = db.execute("PRAGMA foreign_keys")
        fk = cursor.fetchone()[0]
        assert fk == 1

    def test_execute_query(self, db: SQLiteManager):
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        db.execute("INSERT INTO test (name) VALUES (?)", ("hello",))
        db.commit()
        cursor = db.execute("SELECT name FROM test")
        row = cursor.fetchone()
        assert row["name"] == "hello"

    def test_execute_raises_on_bad_sql(self, db: SQLiteManager):
        with pytest.raises(DatabaseError, match="SQL execution failed"):
            db.execute("INVALID SQL STATEMENT")

    def test_executescript(self, db: SQLiteManager):
        db.executescript("""
            CREATE TABLE multi_1 (id INTEGER PRIMARY KEY);
            CREATE TABLE multi_2 (id INTEGER PRIMARY KEY);
        """)
        assert db.table_exists("multi_1")
        assert db.table_exists("multi_2")

    def test_executescript_raises_on_error(self, db: SQLiteManager):
        with pytest.raises(DatabaseError, match="script execution failed"):
            db.executescript("CREATE TABLE ok (id INTEGER); INVALID;")

    def test_table_exists(self, db: SQLiteManager):
        assert db.table_exists("nonexistent") is False
        db.execute("CREATE TABLE exists_test (id INTEGER)")
        db.commit()
        assert db.table_exists("exists_test") is True

    def test_context_manager_commits(self, tmp_db_path: str):
        with SQLiteManager(tmp_db_path) as db:
            db.execute("CREATE TABLE ctx_test (id INTEGER)")
            db.execute("INSERT INTO ctx_test (id) VALUES (1)")

        # Verify data persisted
        manager = SQLiteManager(tmp_db_path)
        manager.connect()
        cursor = manager.execute("SELECT id FROM ctx_test")
        assert cursor.fetchone()[0] == 1
        manager.close()

    def test_context_manager_rollbacks_on_error(self, tmp_db_path: str):
        manager = SQLiteManager(tmp_db_path)
        manager.connect()
        manager.execute("CREATE TABLE rollback_test (id INTEGER)")
        manager.commit()
        manager.close()

        try:
            with SQLiteManager(tmp_db_path) as db:
                db.execute("INSERT INTO rollback_test (id) VALUES (99)")
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Value should not be committed
        manager = SQLiteManager(tmp_db_path)
        manager.connect()
        cursor = manager.execute("SELECT COUNT(*) FROM rollback_test")
        assert cursor.fetchone()[0] == 0
        manager.close()

    def test_db_path_property(self, tmp_db_path: str):
        manager = SQLiteManager(tmp_db_path)
        assert manager.db_path == tmp_db_path

    def test_no_wal_mode(self, tmp_path: Path):
        db_path = str(tmp_path / "nowal.db")
        manager = SQLiteManager(db_path, wal_mode=False)
        manager.connect()
        cursor = manager.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        # Without explicit WAL, SQLite defaults to 'delete' or similar
        assert mode != "wal"
        manager.close()
