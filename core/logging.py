"""Structured logging for the trading system.

Provides JSON-structured logging for audit trail and operational monitoring.
All log entries include timestamp, level, source, and optional metadata.

See implementation_spec.md §19.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for audit trail.

    Every log line is a valid JSON object with:
        - timestamp (ISO 8601 UTC)
        - level
        - source (logger name)
        - message
        - metadata (optional extra fields)
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "source": record.name,
            "message": record.getMessage(),
        }
        # Attach extra metadata if present
        if hasattr(record, "metadata"):
            entry["metadata"] = record.metadata

        # Attach exception info
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(entry, default=str)


class HumanFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(self) -> None:
        super().__init__(fmt=self.FORMAT, datefmt=self.DATE_FORMAT)


def setup_logging(
    level: str = "DEBUG",
    log_file: str | None = None,
    structured: bool = True,
) -> logging.Logger:
    """Configure the root trading system logger.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional file path for log output.
        structured: If True, use JSON formatting; otherwise human-readable.

    Returns:
        Configured root logger for the trading system.
    """
    root_logger = logging.getLogger("trading")
    root_logger.setLevel(getattr(logging, level.upper(), logging.DEBUG))

    # Clear existing handlers (prevents duplicates on re-init)
    root_logger.handlers.clear()

    # Choose formatter
    formatter: logging.Formatter
    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = HumanFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the 'trading' namespace.

    Usage:
        logger = get_logger(__name__)
        logger.info("Trade submitted", extra={"metadata": {"trade_id": "TRD-001"}})
    """
    return logging.getLogger(f"trading.{name}")
