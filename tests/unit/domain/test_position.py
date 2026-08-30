"""Tests for core.domain.position — Position model with PnL calculations."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.domain.enums import PositionSide
from core.domain.position import Position

_NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _pos(**kw):
    d = {
        "position_id": "POS-001",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.5,
        "entry_price": 42500.0,
        "current_price": 43000.0,
        "total_fees": 42.50,
        "total_funding": 5.0,
        "total_slippage": 10.0,
        "strategy_id": "breakout",
        "strategy_version": "2.1",
        "opened_at": _NOW.isoformat(),
        "updated_at": _NOW.isoformat(),
    }
    d.update(kw)
    return d


class TestPositionValid:
    def test_long_position(self):
        p = Position(**_pos())
        assert p.side == PositionSide.LONG
        assert p.quantity == 0.5

    def test_short_position(self):
        p = Position(
            **_pos(
                side="SHORT",
                entry_price=43000.0,
                current_price=42500.0,
            )
        )
        assert p.side == PositionSide.SHORT


class TestPositionPnL:
    """PnL calculations per architecture §11."""

    def test_long_profit(self):
        p = Position(**_pos(entry_price=42500.0, current_price=43000.0))
        assert p.gross_pnl == pytest.approx(250.0)

    def test_long_loss(self):
        p = Position(**_pos(entry_price=42500.0, current_price=42000.0))
        assert p.gross_pnl == pytest.approx(-250.0)

    def test_short_profit(self):
        p = Position(
            **_pos(
                side="SHORT",
                entry_price=43000.0,
                current_price=42500.0,
            )
        )
        assert p.gross_pnl == pytest.approx(250.0)

    def test_short_loss(self):
        p = Position(
            **_pos(
                side="SHORT",
                entry_price=42500.0,
                current_price=43000.0,
            )
        )
        assert p.gross_pnl == pytest.approx(-250.0)

    def test_net_pnl(self):
        """Net PnL = Gross - fees - slippage - funding."""
        p = Position(
            **_pos(
                entry_price=42500.0,
                current_price=43000.0,
                total_fees=42.50,
                total_slippage=10.0,
                total_funding=5.0,
            )
        )
        expected_net = 250.0 - 42.50 - 10.0 - 5.0
        assert p.net_pnl == pytest.approx(expected_net)

    def test_zero_costs_net_equals_gross(self):
        p = Position(**_pos(total_fees=0, total_funding=0, total_slippage=0))
        assert p.net_pnl == pytest.approx(p.gross_pnl)


class TestPositionProperties:
    def test_notional(self):
        p = Position(**_pos(current_price=43000.0, quantity=0.5))
        assert p.notional == pytest.approx(21500.0)

    def test_entry_notional(self):
        p = Position(**_pos(entry_price=42500.0, quantity=0.5))
        assert p.entry_notional == pytest.approx(21250.0)

    def test_return_pct(self):
        p = Position(
            **_pos(
                entry_price=42500.0,
                current_price=43000.0,
                quantity=0.5,
                total_fees=0,
                total_funding=0,
                total_slippage=0,
            )
        )
        expected = 250.0 / 21250.0
        assert p.return_pct == pytest.approx(expected)


class TestPositionInvalid:
    def test_zero_quantity(self):
        with pytest.raises(ValidationError):
            Position(**_pos(quantity=0))

    def test_negative_quantity(self):
        with pytest.raises(ValidationError):
            Position(**_pos(quantity=-0.1))

    def test_zero_entry_price(self):
        with pytest.raises(ValidationError):
            Position(**_pos(entry_price=0))

    def test_zero_current_price(self):
        with pytest.raises(ValidationError):
            Position(**_pos(current_price=0))

    def test_negative_fees(self):
        with pytest.raises(ValidationError):
            Position(**_pos(total_fees=-1.0))

    def test_negative_slippage(self):
        with pytest.raises(ValidationError):
            Position(**_pos(total_slippage=-1.0))

    def test_empty_position_id(self):
        with pytest.raises(ValidationError):
            Position(**_pos(position_id=""))

    def test_empty_symbol(self):
        with pytest.raises(ValidationError):
            Position(**_pos(symbol=""))

    def test_invalid_side(self):
        with pytest.raises(ValidationError):
            Position(**_pos(side="FLAT"))


class TestPositionSerialization:
    def test_json_round_trip(self):
        original = Position(**_pos())
        restored = Position.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_dict_round_trip(self):
        original = Position(**_pos())
        restored = Position(**original.model_dump())
        assert restored == original
