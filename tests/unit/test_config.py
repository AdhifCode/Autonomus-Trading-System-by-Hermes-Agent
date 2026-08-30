"""Tests for core.config — configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.config import (
    VALID_TRADING_MODES,
    DatabaseConfig,
    ExchangeConfig,
    LoggingConfig,
    ObsidianConfig,
    TradingConfig,
    load_config,
    load_yaml,
)
from core.errors import ConfigError


class TestLoadYaml:
    """Test YAML file loading."""

    def test_loads_valid_yaml(self, tmp_path: Path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("key: value\nnested:\n  inner: 42\n")
        data = load_yaml(yaml_file)
        assert data["key"] == "value"
        assert data["nested"]["inner"] == 42

    def test_raises_on_missing_file(self):
        with pytest.raises(ConfigError, match="not found"):
            load_yaml("/nonexistent/path.yaml")

    def test_raises_on_invalid_yaml(self, tmp_path: Path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(":::invalid:::\n  - ][")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_yaml(yaml_file)

    def test_raises_on_non_dict_yaml(self, tmp_path: Path):
        yaml_file = tmp_path / "list.yaml"
        yaml_file.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigError, match="Expected dict"):
            load_yaml(yaml_file)


class TestTradingModes:
    """Verify all 7 trading modes from architecture §34."""

    def test_all_modes_present(self):
        expected = {
            "DEVELOPMENT",
            "BACKTEST",
            "SHADOW",
            "PAPER",
            "TESTNET",
            "LIMITED_LIVE",
            "LIVE",
        }
        assert VALID_TRADING_MODES == expected

    def test_invalid_mode_raises(self):
        with pytest.raises(ConfigError, match="Invalid trading mode"):
            TradingConfig(
                trading_mode="INVALID",
                database=DatabaseConfig("test.db"),
                exchange=ExchangeConfig(),
                risk_policy_file="risk.yaml",
                logging=LoggingConfig(),
                obsidian=ObsidianConfig(),
            )

    @pytest.mark.parametrize("mode", sorted(VALID_TRADING_MODES))
    def test_all_valid_modes_accepted(self, mode):
        cfg = TradingConfig(
            trading_mode=mode,
            database=DatabaseConfig("test.db"),
            exchange=ExchangeConfig(),
            risk_policy_file="risk.yaml",
            logging=LoggingConfig(),
            obsidian=ObsidianConfig(),
        )
        assert cfg.trading_mode == mode


class TestTradingConfig:
    """Test TradingConfig properties."""

    def test_is_live_for_live_modes(self):
        for mode in ("LIMITED_LIVE", "LIVE"):
            cfg = TradingConfig(
                trading_mode=mode,
                database=DatabaseConfig("test.db"),
                exchange=ExchangeConfig(),
                risk_policy_file="risk.yaml",
                logging=LoggingConfig(),
                obsidian=ObsidianConfig(),
            )
            assert cfg.is_live is True

    def test_is_not_live_for_dev_modes(self):
        for mode in ("DEVELOPMENT", "BACKTEST", "SHADOW", "PAPER", "TESTNET"):
            cfg = TradingConfig(
                trading_mode=mode,
                database=DatabaseConfig("test.db"),
                exchange=ExchangeConfig(),
                risk_policy_file="risk.yaml",
                logging=LoggingConfig(),
                obsidian=ObsidianConfig(),
            )
            assert cfg.is_live is False

    def test_env_name(self):
        cfg = TradingConfig(
            trading_mode="DEVELOPMENT",
            database=DatabaseConfig("test.db"),
            exchange=ExchangeConfig(),
            risk_policy_file="risk.yaml",
            logging=LoggingConfig(),
            obsidian=ObsidianConfig(),
            env_name="staging",
        )
        assert cfg.env_name == "staging"


class TestLoadConfig:
    """Test full configuration loading pipeline."""

    def test_loads_from_yaml(self, config_dir: Path):
        cfg = load_config(
            env_name="test",
            config_dir=config_dir,
            dotenv_path="/dev/null",
        )
        assert cfg.trading_mode == "DEVELOPMENT"
        assert cfg.exchange.adapter == "mock"
        assert cfg.exchange.simulated_latency_ms == 50
        assert cfg.database.wal_mode is True

    def test_env_var_overrides_yaml(self, config_dir: Path):
        os.environ["TRADING_MODE"] = "PAPER"
        try:
            cfg = load_config(
                env_name="test",
                config_dir=config_dir,
                dotenv_path="/dev/null",
            )
            assert cfg.trading_mode == "PAPER"
        finally:
            del os.environ["TRADING_MODE"]

    def test_database_path_override(self, config_dir: Path, tmp_path: Path):
        override_path = str(tmp_path / "override.db")
        os.environ["DATABASE_PATH"] = override_path
        try:
            cfg = load_config(
                env_name="test",
                config_dir=config_dir,
                dotenv_path="/dev/null",
            )
            assert cfg.database.path == override_path
        finally:
            del os.environ["DATABASE_PATH"]

    def test_missing_env_raises(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(ConfigError, match="not found"):
            load_config(env_name="nonexistent", config_dir=empty_dir)

    def test_repr(self, config_dir: Path):
        cfg = load_config(
            env_name="test",
            config_dir=config_dir,
            dotenv_path="/dev/null",
        )
        r = repr(cfg)
        assert "DEVELOPMENT" in r
        assert "mock" in r


class TestSubConfigs:
    """Test individual config data classes."""

    def test_database_config(self):
        db = DatabaseConfig("test.db", wal_mode=False)
        assert db.path == "test.db"
        assert db.wal_mode is False
        assert "test.db" in repr(db)

    def test_exchange_config(self):
        ex = ExchangeConfig(adapter="binance", testnet=True, simulated_latency_ms=200)
        assert ex.adapter == "binance"
        assert ex.testnet is True
        assert ex.simulated_latency_ms == 200

    def test_logging_config_normalizes_level(self):
        log = LoggingConfig(level="debug")
        assert log.level == "DEBUG"

    def test_obsidian_config_defaults(self):
        obs = ObsidianConfig()
        assert obs.vault_path == "~/obsidian-vault"
        assert obs.enabled is False
