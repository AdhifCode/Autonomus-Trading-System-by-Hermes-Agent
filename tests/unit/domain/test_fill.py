"""Tests for core.domain.fill — Fill model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.domain.enums import OrderSide
from core.domain.fill import Fill

_NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _fill(**kw):
    d = {
        "fill_id": "FILL-001",
        "order_id": "TRD-20260828-000001",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.5,
        "price": 42500.0,
        "fee": 21.25,
        "fee_currency": "USDT",
        "timestamp": _NOW.isoformat(),
    }
    d.update(kw)
    return d


class TestFillValid:
    def test_basic(self):
        f = Fill(**_fill())
        assert f.fill_id == "FILL-001"
        assert f.side == OrderSide.BUY

    def test_notional(self):
        f = Fill(**_fill())
        assert f.notional == pytest.approx(42500.0 * 0.5)

    def test_net_cost(self):
        f = Fill(**_fill())
        assert f.net_cost == pytest.approx(42500.0 * 0.5 + 21.25)

    def test_zero_fee(self):
        f = Fill(**_fill(fee=0.0))
        assert f.fee == 0.0
        assert f.net_cost == f.notional


class TestFillInvalid:
    def test_zero_quantity(self):
        with pytest.raises(ValidationError):
            Fill(**_fill(quantity=0))

    def test_negative_quantity(self):
        with pytest.raises(ValidationError):
            Fill(**_fill(quantity=-0.1))

    def test_zero_price(self):
        with pytest.raises(ValidationError):
            Fill(**_fill(price=0))

    def test_negative_price(self):
        with pytest.raises(ValidationError):
            Fill(**_fill(price=-100.0))

    def test_negative_fee(self):
        with pytest.raises(ValidationError):
            Fill(**_fill(fee=-1.0))

    def test_empty_fill_id(self):
        with pytest.raises(ValidationError):
            Fill(**_fill(fill_id=""))

    def test_empty_order_id(self):
        with pytest.raises(ValidationError):
            Fill(**_fill(order_id=""))

    def test_empty_symbol(self):
        with pytest.raises(ValidationError):
            Fill(**_fill(symbol=""))

    def test_empty_fee_currency(self):
        with pytest.raises(ValidationError):
            Fill(**_fill(fee_currency=""))

    def test_invalid_side(self):
        with pytest.raises(ValidationError):
            Fill(**_fill(side="HOLD"))


class TestFillSerialization:
    def test_json_round_trip(self):
        original = Fill(**_fill())
        restored = Fill.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_dict_round_trip(self):
        original = Fill(**_fill())
        restored = Fill(**original.model_dump())
        assert restored == original
