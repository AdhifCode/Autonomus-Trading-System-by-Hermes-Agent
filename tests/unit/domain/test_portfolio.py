"""Tests for core.domain.portfolio — PortfolioState model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.domain.portfolio import PortfolioState

_NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _portfolio(**kw):
    d = {
        "balance": 100000.0,
        "equity": 102000.0,
        "available_margin": 80000.0,
        "exposure": 20000.0,
        "realized_pnl": 500.0,
        "unrealized_pnl": 1500.0,
        "daily_pnl": 200.0,
        "drawdown": 0.02,
        "timestamp": _NOW.isoformat(),
    }
    d.update(kw)
    return d


class TestPortfolioValid:
    def test_basic(self):
        ps = PortfolioState(**_portfolio())
        assert ps.balance == 100000.0
        assert ps.positions == []
        assert ps.open_orders == []

    def test_total_pnl(self):
        ps = PortfolioState(**_portfolio(realized_pnl=500.0, unrealized_pnl=1500.0))
        assert ps.total_pnl == pytest.approx(2000.0)

    def test_position_count_zero(self):
        ps = PortfolioState(**_portfolio())
        assert ps.position_count == 0

    def test_open_order_count_zero(self):
        ps = PortfolioState(**_portfolio())
        assert ps.open_order_count == 0


class TestPortfolioDrawdown:
    def test_zero_drawdown(self):
        ps = PortfolioState(**_portfolio(drawdown=0.0))
        assert ps.drawdown == 0.0

    def test_max_drawdown(self):
        ps = PortfolioState(**_portfolio(drawdown=1.0))
        assert ps.drawdown == 1.0

    def test_negative_drawdown_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioState(**_portfolio(drawdown=-0.01))

    def test_over_max_drawdown_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioState(**_portfolio(drawdown=1.01))


class TestPortfolioExposure:
    def test_negative_exposure_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioState(**_portfolio(exposure=-1.0))


class TestPortfolioSerialization:
    def test_json_round_trip(self):
        original = PortfolioState(**_portfolio())
        restored = PortfolioState.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_dict_round_trip(self):
        original = PortfolioState(**_portfolio())
        restored = PortfolioState(**original.model_dump())
        assert restored == original
