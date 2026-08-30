"""DuckDB Analytics Engine Module.

Integrates DuckDB for fast SQL queries, aggregations, and feature extractions over
Parquet market data files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


class DuckDBEngine:
    """Analytics database wrapper utilizing DuckDB for querying Parquet datasets."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn = duckdb.connect(db_path)

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return rows as list of dictionaries."""
        cursor = self.conn.execute(sql, params or [])
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def register_parquet(self, view_name: str, parquet_path: str | Path) -> None:
        """Register a Parquet file as a DuckDB virtual SQL table/view."""
        path_str = str(parquet_path)
        self.conn.execute(
            f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{path_str}')"  # noqa: S608
        )

    def get_ohlcv_summary(self, view_name: str) -> dict[str, Any]:
        """Compute aggregate summary metrics over a market dataset view."""
        res = self.query(f"""
            SELECT
                count(*) as total_bars,
                min(timestamp) as start_time,
                max(timestamp) as end_time,
                min(low) as min_price,
                max(high) as max_price,
                sum(volume) as total_volume
            FROM {view_name}
        """)  # noqa: S608
        return res[0] if res else {}

    def close(self) -> None:
        """Close DuckDB connection."""
        self.conn.close()


__all__ = ["DuckDBEngine"]
