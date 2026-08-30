"""Tests for core.logging — structured logging setup."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.logging import HumanFormatter, StructuredFormatter, get_logger, setup_logging


class TestStructuredFormatter:
    """Test JSON structured log formatting."""

    def test_produces_valid_json(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="trading.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["source"] == "trading.test"
        assert parsed["message"] == "test message"
        assert "timestamp" in parsed

    def test_includes_metadata(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="trading.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        record.metadata = {"trade_id": "TRD-001"}  # type: ignore[attr-defined]
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["metadata"]["trade_id"] == "TRD-001"

    def test_includes_exception_info(self):
        formatter = StructuredFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="trading.test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="error occurred",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["exception"]["type"] == "ValueError"
        assert "test error" in parsed["exception"]["message"]

    def test_timestamp_is_iso8601(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        # Should be parseable ISO 8601
        assert "T" in parsed["timestamp"]
        assert parsed["timestamp"].endswith("+00:00")


class TestHumanFormatter:
    """Test human-readable formatting."""

    def test_produces_readable_output(self):
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="trading.test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="something happened",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "WARNING" in output
        assert "trading.test" in output
        assert "something happened" in output


class TestSetupLogging:
    """Test logging setup."""

    def test_returns_root_logger(self):
        logger = setup_logging(level="DEBUG", structured=False)
        assert logger.name == "trading"
        assert logger.level == logging.DEBUG

    def test_structured_mode(self):
        logger = setup_logging(level="INFO", structured=True)
        assert any(isinstance(h.formatter, StructuredFormatter) for h in logger.handlers)

    def test_human_mode(self):
        logger = setup_logging(level="INFO", structured=False)
        assert any(isinstance(h.formatter, HumanFormatter) for h in logger.handlers)

    def test_file_handler_created(self, tmp_path: Path):
        log_file = str(tmp_path / "test.log")
        logger = setup_logging(level="DEBUG", log_file=log_file, structured=False)
        logger.info("test file log")
        assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)
        assert Path(log_file).exists()

    def test_creates_log_directory(self, tmp_path: Path):
        log_file = str(tmp_path / "subdir" / "nested" / "test.log")
        setup_logging(level="DEBUG", log_file=log_file)
        assert Path(log_file).parent.exists()

    def test_clears_existing_handlers(self):
        """Re-initialization should not create duplicate handlers."""
        setup_logging(level="DEBUG", structured=False)
        handler_count_1 = len(logging.getLogger("trading").handlers)
        setup_logging(level="DEBUG", structured=False)
        handler_count_2 = len(logging.getLogger("trading").handlers)
        assert handler_count_1 == handler_count_2


class TestGetLogger:
    """Test child logger creation."""

    def test_creates_namespaced_logger(self):
        logger = get_logger("risk.engine")
        assert logger.name == "trading.risk.engine"

    def test_different_names_different_loggers(self):
        l1 = get_logger("module_a")
        l2 = get_logger("module_b")
        assert l1 is not l2
        assert l1.name != l2.name
