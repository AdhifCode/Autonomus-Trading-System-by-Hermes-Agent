"""Configuration system for the trading system.

Loads environment-specific YAML configuration and merges with
environment variables (.env). Provides a typed, validated
configuration object.

Environment resolution order:
    1. Environment variables (highest priority)
    2. .env file
    3. YAML config file (lowest priority)

See implementation_spec.md §20 and architecture.md §34.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from core.errors import ConfigError

# ---------------------------------------------------------------------------
# Config data classes (plain, no Pydantic yet — that's Phase 2)
# ---------------------------------------------------------------------------


class DatabaseConfig:
    """SQLite database configuration."""

    __slots__ = ("path", "wal_mode")

    def __init__(self, path: str, wal_mode: bool = True) -> None:
        self.path = path
        self.wal_mode = wal_mode

    def __repr__(self) -> str:
        return f"DatabaseConfig(path={self.path!r}, wal_mode={self.wal_mode})"


class ExchangeConfig:
    """Exchange adapter configuration."""

    __slots__ = ("adapter", "simulated_latency_ms", "testnet")

    def __init__(
        self,
        adapter: str = "mock",
        testnet: bool = True,
        simulated_latency_ms: int = 100,
    ) -> None:
        self.adapter = adapter
        self.testnet = testnet
        self.simulated_latency_ms = simulated_latency_ms

    def __repr__(self) -> str:
        return (
            f"ExchangeConfig(adapter={self.adapter!r}, "
            f"testnet={self.testnet}, "
            f"simulated_latency_ms={self.simulated_latency_ms})"
        )


class LoggingConfig:
    """Logging configuration."""

    __slots__ = ("file", "level", "structured")

    def __init__(
        self,
        level: str = "DEBUG",
        file: str | None = None,
        structured: bool = True,
    ) -> None:
        self.level = level.upper()
        self.file = file
        self.structured = structured

    def __repr__(self) -> str:
        return (
            f"LoggingConfig(level={self.level!r}, file={self.file!r}, structured={self.structured})"
        )


class ObsidianConfig:
    """Obsidian knowledge layer configuration."""

    __slots__ = ("enabled", "vault_path")

    def __init__(
        self,
        vault_path: str = "~/obsidian-vault",
        enabled: bool = False,
    ) -> None:
        self.vault_path = vault_path
        self.enabled = enabled

    def __repr__(self) -> str:
        return f"ObsidianConfig(vault_path={self.vault_path!r}, enabled={self.enabled})"


# ---------------------------------------------------------------------------
# Valid trading modes (architecture §34)
# ---------------------------------------------------------------------------

VALID_TRADING_MODES = frozenset(
    {
        "DEVELOPMENT",
        "BACKTEST",
        "SHADOW",
        "PAPER",
        "TESTNET",
        "LIMITED_LIVE",
        "LIVE",
    }
)


class TradingConfig:
    """Root configuration for the trading system."""

    __slots__ = (
        "_env_name",
        "database",
        "exchange",
        "logging",
        "obsidian",
        "risk_policy_file",
        "trading_mode",
    )

    def __init__(
        self,
        trading_mode: str,
        database: DatabaseConfig,
        exchange: ExchangeConfig,
        risk_policy_file: str,
        logging: LoggingConfig,
        obsidian: ObsidianConfig,
        env_name: str = "development",
    ) -> None:
        if trading_mode not in VALID_TRADING_MODES:
            raise ConfigError(
                f"Invalid trading mode: {trading_mode!r}. "
                f"Valid modes: {sorted(VALID_TRADING_MODES)}"
            )
        self.trading_mode = trading_mode
        self.database = database
        self.exchange = exchange
        self.risk_policy_file = risk_policy_file
        self.logging = logging
        self.obsidian = obsidian
        self._env_name = env_name

    @property
    def env_name(self) -> str:
        """Return the environment name (e.g. 'development', 'paper')."""
        return self._env_name

    @property
    def is_live(self) -> bool:
        """Return True if this is a live-trading configuration."""
        return self.trading_mode in ("LIMITED_LIVE", "LIVE")

    def __repr__(self) -> str:
        return (
            f"TradingConfig(mode={self.trading_mode!r}, "
            f"env={self._env_name!r}, "
            f"exchange={self.exchange.adapter!r})"
        )


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------


def _deep_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dicts."""
    current: Any = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    filepath = Path(path)
    if not filepath.exists():
        raise ConfigError(f"Configuration file not found: {filepath}")
    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {filepath}: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError(f"Expected dict in {filepath}, got {type(data).__name__}")
    return data


def load_config(
    env_name: str = "development",
    config_dir: str | Path = "configs/environments",
    dotenv_path: str | Path | None = None,
) -> TradingConfig:
    """Load configuration for the given environment.

    Precedence: env vars > .env > YAML config.

    Args:
        env_name: Environment name (maps to configs/environments/{name}.yaml).
        config_dir: Directory containing environment YAML files.
        dotenv_path: Path to .env file. If None, searches working directory.

    Returns:
        Validated TradingConfig instance.

    Raises:
        ConfigError: If configuration is invalid or missing.
    """
    # Load .env file (if exists)
    if dotenv_path:
        load_dotenv(Path(dotenv_path))
    else:
        load_dotenv()  # searches cwd

    # Load YAML
    yaml_path = Path(config_dir) / f"{env_name}.yaml"
    data = load_yaml(yaml_path)

    # Resolve with env var overrides
    trading_mode = os.getenv("TRADING_MODE", data.get("trading_mode", "DEVELOPMENT"))

    db_default = _deep_get(data, "database", "path", default="data/trading.db")
    db_path = os.getenv("DATABASE_PATH", db_default)
    db_wal = _deep_get(data, "database", "wal_mode", default=True)

    ex_adapter = _deep_get(data, "exchange", "adapter", default="mock")
    ex_testnet = _deep_get(data, "exchange", "testnet", default=True)
    ex_latency = _deep_get(data, "exchange", "simulated_latency_ms", default=100)

    risk_file = os.getenv(
        "RISK_POLICY_FILE",
        _deep_get(data, "risk", "policy_file", default="configs/risk.yaml"),
    )

    log_level = os.getenv("LOG_LEVEL", _deep_get(data, "logging", "level", default="DEBUG"))
    log_file = os.getenv("LOG_FILE", _deep_get(data, "logging", "file", default=None))
    log_structured = _deep_get(data, "logging", "structured", default=True)

    obs_path = os.getenv(
        "OBSIDIAN_VAULT_PATH",
        _deep_get(data, "obsidian", "vault_path", default="~/obsidian-vault"),
    )
    obs_enabled = _deep_get(data, "obsidian", "enabled", default=False)

    return TradingConfig(
        trading_mode=trading_mode,
        database=DatabaseConfig(path=db_path, wal_mode=db_wal),
        exchange=ExchangeConfig(
            adapter=ex_adapter,
            testnet=ex_testnet,
            simulated_latency_ms=ex_latency,
        ),
        risk_policy_file=risk_file,
        logging=LoggingConfig(level=log_level, file=log_file, structured=log_structured),
        obsidian=ObsidianConfig(vault_path=obs_path, enabled=obs_enabled),
        env_name=env_name,
    )
