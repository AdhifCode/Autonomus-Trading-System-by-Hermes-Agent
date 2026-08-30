"""Tests for core.domain.strategy — StrategyVersion model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.domain.enums import StrategyLifecycle
from core.domain.strategy import StrategyVersion

_NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _strategy(**kw):
    d = {
        "strategy_id": "breakout",
        "version": "2.1",
        "lifecycle": "PRODUCTION",
        "parameters": {"lookback_period": 20, "atr_multiplier": 2.0},
        "risk_overrides": {"max_position_size_pct": 0.03},
        "applicable_regimes": ["BULL", "SIDEWAYS"],
        "metadata": {"backtest_sharpe": 1.45},
        "created_at": _NOW.isoformat(),
        "created_by": "human",
    }
    d.update(kw)
    return d


class TestStrategyVersionValid:
    def test_basic(self):
        sv = StrategyVersion(**_strategy())
        assert sv.strategy_id == "breakout"
        assert sv.version == "2.1"
        assert sv.lifecycle == StrategyLifecycle.PRODUCTION

    def test_qualified_name(self):
        sv = StrategyVersion(**_strategy())
        assert sv.qualified_name == "breakout:2.1"

    def test_is_production(self):
        sv = StrategyVersion(**_strategy(lifecycle="PRODUCTION"))
        assert sv.is_production
        assert not sv.is_deprecated

    def test_is_deprecated(self):
        sv = StrategyVersion(**_strategy(lifecycle="DEPRECATED"))
        assert sv.is_deprecated
        assert not sv.is_production

    def test_idea_lifecycle(self):
        sv = StrategyVersion(**_strategy(lifecycle="IDEA"))
        assert not sv.is_production
        assert not sv.is_deprecated

    def test_default_empty_fields(self):
        sv = StrategyVersion(
            strategy_id="test",
            version="1.0",
            created_at=_NOW,
            created_by="human",
        )
        assert sv.parameters == {}
        assert sv.risk_overrides == {}
        assert sv.applicable_regimes == []
        assert sv.lifecycle == StrategyLifecycle.IDEA


class TestStrategyVersionInvalid:
    def test_empty_strategy_id(self):
        with pytest.raises(ValidationError):
            StrategyVersion(**_strategy(strategy_id=""))

    def test_empty_version(self):
        with pytest.raises(ValidationError):
            StrategyVersion(**_strategy(version=""))

    def test_empty_created_by(self):
        with pytest.raises(ValidationError):
            StrategyVersion(**_strategy(created_by=""))

    def test_invalid_lifecycle(self):
        with pytest.raises(ValidationError):
            StrategyVersion(**_strategy(lifecycle="RUNNING"))

    def test_invalid_regime_in_list(self):
        with pytest.raises(ValidationError):
            StrategyVersion(**_strategy(applicable_regimes=["CRASH"]))


class TestStrategyVersionSerialization:
    def test_json_round_trip(self):
        original = StrategyVersion(**_strategy())
        restored = StrategyVersion.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_dict_round_trip(self):
        original = StrategyVersion(**_strategy())
        restored = StrategyVersion(**original.model_dump())
        assert restored == original
