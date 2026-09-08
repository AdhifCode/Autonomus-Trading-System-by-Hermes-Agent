"""SQLite connection manager for the trading system.

SQLite is the canonical operational database (architecture.md §14).
Configured with WAL mode for concurrent read/write support.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.errors import DatabaseError
from core.logging import get_logger

logger = get_logger(__name__)


# SQLite pragmas for operational workloads
_PRAGMAS = [
    "PRAGMA journal_mode = WAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA cache_size = -64000",  # 64MB cache
    "PRAGMA temp_store = MEMORY",
]


class SQLiteManager:
    """Manages SQLite database connections for the trading system.

    Thread-safety: Each SQLiteManager instance holds one connection.
    For concurrent access, create separate instances (WAL mode allows
    concurrent readers with one writer).
    """

    def __init__(self, db_path: str = "trading_system.db", wal_mode: bool = True) -> None:
        self._db_path = db_path
        self._wal_mode = wal_mode
        self._connection: sqlite3.Connection | None = None
        self._in_transaction: bool = False

    @property
    def db_path(self) -> str:
        """Get the database path."""
        return self._db_path

    @property
    def is_connected(self) -> bool:
        """Check if database connection is active."""
        return self._connection is not None

    def connect(self) -> sqlite3.Connection:
        """Connect to SQLite database and configure PRAGMA settings.

        Returns:
            Active sqlite3.Connection instance.

        Raises:
            DatabaseError: If connection fails.
        """
        if self._connection is not None:
            return self._connection

        try:
            db_file = Path(self._db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)

            self._connection = sqlite3.connect(
                self._db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row

            # Apply pragmas
            if self._wal_mode:
                for pragma in _PRAGMAS:
                    self._connection.execute(pragma)
            else:
                # Still enable foreign keys and timeout even without WAL
                self._connection.execute("PRAGMA foreign_keys = ON")
                self._connection.execute("PRAGMA busy_timeout = 5000")

            logger.info(
                "Database connected",
                extra={"metadata": {"path": self._db_path, "wal": self._wal_mode}},
            )
            return self._connection

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to connect to database: {e}") from e

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            try:
                self.commit()
            except Exception as commit_err:
                logger.debug("Failed to commit on close: %s", commit_err)
            self._connection.close()
            self._connection = None
            logger.info(
                "Database disconnected",
                extra={"metadata": {"path": self._db_path}},
            )

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> sqlite3.Cursor:
        """Execute a single SQL statement.

        Args:
            sql: SQL statement to execute.
            params: Optional parameters for parameterized queries.

        Returns:
            sqlite3.Cursor with results.

        Raises:
            DatabaseError: If execution fails.
        """
        conn = self.connect()
        try:
            if params:
                return conn.execute(sql, params)
            return conn.execute(sql)
        except sqlite3.Error as e:
            raise DatabaseError(f"SQL execution failed: {e}") from e

    def executescript(self, sql_script: str) -> None:
        """Execute a multi-statement SQL script.

        Args:
            sql_script: SQL script with multiple statements.

        Raises:
            DatabaseError: If execution fails.
        """
        conn = self.connect()
        try:
            conn.executescript(sql_script)
        except sqlite3.Error as e:
            raise DatabaseError(f"SQL script execution failed: {e}") from e

    def commit(self) -> None:
        """Commit the current transaction."""
        if self._connection is not None:
            self._connection.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        if self._connection is not None:
            self._connection.rollback()

    def __enter__(self) -> SQLiteManager:
        self.connect()
        self._in_transaction = True
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any) -> None:
        try:
            if exc_type is not None:
                self.rollback()
            else:
                self.commit()
        finally:
            self._in_transaction = False
            self.close()

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        cursor = self.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return cursor.fetchone() is not None
