"""Shared test fixtures and global pytest configuration.

Ensures the test suite runs with virtual environment precedence and isolates
the runtime from host system-wide packages (e.g. incompatible Debian pandas/numpy).
"""
# ruff: noqa: E402, I001

from __future__ import annotations

import os
from pathlib import Path
import sys

# Shield virtual environment imports from host Debian/Ubuntu system dist-packages
sys.path = [p for p in sys.path if not p.startswith("/usr/lib/python3/dist-packages")]

import pytest

from adapters.database.sqlite import SQLiteManager
from core.config import TradingConfig, load_config


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for test artifacts."""
    return tmp_path


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Provide a temporary database path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def db(tmp_db_path: str) -> SQLiteManager:
    """Provide a connected SQLiteManager for testing."""
    manager = SQLiteManager(tmp_db_path)
    manager.connect()
    yield manager  # type: ignore[misc]
    manager.close()


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with a test environment file."""
    env_dir = tmp_path / "configs" / "environments"
    env_dir.mkdir(parents=True)

    test_config = """\
trading_mode: DEVELOPMENT
database:
  path: data/test.db
  wal_mode: true
exchange:
  adapter: mock
  testnet: true
  simulated_latency_ms: 50
risk:
  policy_file: configs/risk.yaml
logging:
  level: DEBUG
  file: null
  structured: false
obsidian:
  vault_path: ~/obsidian-vault
  enabled: false
"""
    (env_dir / "test.yaml").write_text(test_config)
    (env_dir / "development.yaml").write_text(test_config)
    return env_dir


@pytest.fixture
def test_config(config_dir: Path) -> TradingConfig:
    """Provide a TradingConfig loaded from test fixtures."""
    # Clear any env vars that might interfere
    env_vars_to_clear = [
        "TRADING_MODE",
        "DATABASE_PATH",
        "LOG_LEVEL",
        "LOG_FILE",
        "RISK_POLICY_FILE",
        "OBSIDIAN_VAULT_PATH",
    ]
    original_values: dict[str, str | None] = {}
    for var in env_vars_to_clear:
        original_values[var] = os.environ.pop(var, None)

    try:
        cfg = load_config(
            env_name="test",
            config_dir=config_dir,
            dotenv_path="/dev/null",  # skip .env loading
        )
        return cfg
    finally:
        # Restore original env vars
        for var, val in original_values.items():
            if val is not None:
                os.environ[var] = val


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    """Create a temporary migrations directory with test migration files."""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()

    # Create test migration files
    (mig_dir / "001_create_test_table.sql").write_text(
        "CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT NOT NULL);\n"
    )
    (mig_dir / "002_add_column.sql").write_text(
        "ALTER TABLE test_table ADD COLUMN value REAL DEFAULT 0;\n"
    )
    return mig_dir
