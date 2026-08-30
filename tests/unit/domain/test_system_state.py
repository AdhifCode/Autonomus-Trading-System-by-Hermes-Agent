"""Tests for core.domain.system_state — SystemState model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.domain.enums import KillSwitchState, TradingMode
from core.domain.system_state import SystemState

_NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _sys(**kw):
    d = {
        "trading_mode": "PAPER",
        "kill_switch": "ACTIVE",
        "exchange_connected": True,
        "data_healthy": True,
        "last_heartbeat": _NOW.isoformat(),
    }
    d.update(kw)
    return d


class TestSystemStateValid:
    def test_basic(self):
        ss = SystemState(**_sys())
        assert ss.trading_mode == TradingMode.PAPER
        assert ss.kill_switch == KillSwitchState.ACTIVE

    def test_default_empty_errors(self):
        ss = SystemState(**_sys())
        assert ss.active_errors == []


class TestSystemStateHealth:
    def test_healthy(self):
        ss = SystemState(**_sys())
        assert ss.is_healthy

    def test_unhealthy_exchange_disconnected(self):
        ss = SystemState(**_sys(exchange_connected=False))
        assert not ss.is_healthy

    def test_unhealthy_data(self):
        ss = SystemState(**_sys(data_healthy=False))
        assert not ss.is_healthy

    def test_unhealthy_kill_switch(self):
        ss = SystemState(**_sys(kill_switch="SOFT_KILL"))
        assert not ss.is_healthy

    def test_unhealthy_active_errors(self):
        ss = SystemState(**_sys(active_errors=["DB connection lost"]))
        assert not ss.is_healthy


class TestSystemStateCanTrade:
    def test_can_trade_paper(self):
        ss = SystemState(**_sys(trading_mode="PAPER"))
        assert ss.can_trade

    def test_can_trade_live(self):
        ss = SystemState(**_sys(trading_mode="LIVE"))
        assert ss.can_trade

    def test_cannot_trade_development(self):
        ss = SystemState(**_sys(trading_mode="DEVELOPMENT"))
        assert not ss.can_trade

    def test_cannot_trade_backtest(self):
        ss = SystemState(**_sys(trading_mode="BACKTEST"))
        assert not ss.can_trade

    def test_cannot_trade_unhealthy(self):
        ss = SystemState(**_sys(exchange_connected=False))
        assert not ss.can_trade

    def test_cannot_trade_kill_switch(self):
        ss = SystemState(**_sys(kill_switch="HARD_KILL"))
        assert not ss.can_trade


class TestSystemStateInvalid:
    def test_invalid_trading_mode(self):
        with pytest.raises(ValidationError):
            SystemState(**_sys(trading_mode="PRODUCTION"))

    def test_invalid_kill_switch(self):
        with pytest.raises(ValidationError):
            SystemState(**_sys(kill_switch="EMERGENCY"))


class TestSystemStateSerialization:
    def test_json_round_trip(self):
        original = SystemState(**_sys())
        restored = SystemState.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_dict_round_trip(self):
        original = SystemState(**_sys())
        restored = SystemState(**original.model_dump())
        assert restored == original
