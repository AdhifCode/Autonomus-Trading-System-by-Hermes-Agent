"""Parquet Storage Module.

Provides Parquet file read/write operations for historical market data using PyArrow.
Supports directory partitioning by symbol.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from data.validation.checker import Candle


class ParquetStore:
    """Manages reading and writing of market data candles to Parquet files."""

    def __init__(self, base_dir: str | Path = "data/parquet") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _schema(self) -> pa.Schema:
        return pa.schema(
            [
                ("timestamp", pa.timestamp("ms", tz="UTC")),
                ("symbol", pa.string()),
                ("open", pa.float64()),
                ("high", pa.float64()),
                ("low", pa.float64()),
                ("close", pa.float64()),
                ("volume", pa.float64()),
            ]
        )

    def save_candles(
        self, symbol: str, candles: Sequence[Candle], filename: str | None = None
    ) -> Path:
        """Save a list of Candle domain models to a Parquet file."""
        target_name = filename or f"{symbol.lower()}_candles.parquet"
        file_path = self.base_dir / target_name

        data = {
            "timestamp": [c.timestamp for c in candles],
            "symbol": [c.symbol for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }

        table = pa.Table.from_pydict(data, schema=self._schema())
        pq.write_table(table, file_path)
        return file_path

    def load_candles(self, filename: str) -> list[Candle]:
        """Load Candle domain models from a Parquet file."""
        file_path = self.base_dir / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {file_path}")

        table = pq.read_table(file_path)
        pydict = table.to_pydict()

        candles: list[Candle] = []
        for i in range(len(pydict["timestamp"])):
            c = Candle(
                timestamp=pydict["timestamp"][i],
                symbol=pydict["symbol"][i],
                open=float(pydict["open"][i]),
                high=float(pydict["high"][i]),
                low=float(pydict["low"][i]),
                close=float(pydict["close"][i]),
                volume=float(pydict["volume"][i]),
            )
            candles.append(c)

        return candles


__all__ = ["ParquetStore"]
