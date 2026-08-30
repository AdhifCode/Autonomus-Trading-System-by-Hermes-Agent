"""Base repository interface and implementation for SQLite data access."""

from __future__ import annotations

from typing import Generic, TypeVar

from adapters.database.sqlite import SQLiteManager

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Base repository class providing database access."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db
