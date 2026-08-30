"""Tests for core.domain.order — Order and OrderRequest models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.domain.enums import OrderStatus, OrderType
from core.domain.order import Order, OrderRequest

_NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _req(**kw):
    d = {
        "client_order_id": "TRD-20260828-000001",
        "proposal_id": "PRP-20260828-000001",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 0.5,
        "price": 42500.0,
    }
    d.update(kw)
    return d


def _order(**kw):
    d = {
        "client_order_id": "TRD-20260828-000001",
        "proposal_id": "PRP-20260828-000001",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 0.5,
        "price": 42500.0,
        "status": "PENDING",
        "created_at": _NOW.isoformat(),
        "updated_at": _NOW.isoformat(),
    }
    d.update(kw)
    return d


# ---- OrderRequest ----


class TestOrderRequestValid:
    def test_limit(self):
        r = OrderRequest(**_req())
        assert r.client_order_id == "TRD-20260828-000001"
        assert r.quantity == 0.5

    def test_market(self):
        r = OrderRequest(**_req(order_type="MARKET", price=None))
        assert r.order_type == OrderType.MARKET

    def test_stop_market(self):
        r = OrderRequest(**_req(order_type="STOP_MARKET", price=None, stop_price=41000.0))
        assert r.stop_price == 41000.0

    def test_stop_limit(self):
        r = OrderRequest(**_req(order_type="STOP_LIMIT", price=42000.0, stop_price=41000.0))
        assert r.price == 42000.0
        assert r.stop_price == 41000.0


class TestOrderRequestIdFormat:
    @pytest.mark.parametrize(
        "bad_id",
        [
            "TRD-2026-000001",
            "TRD-20260828-00001",
            "PRP-20260828-000001",
            "",
            "trd-20260828-000001",
        ],
    )
    def test_invalid(self, bad_id):
        with pytest.raises(ValidationError):
            OrderRequest(**_req(client_order_id=bad_id))


class TestOrderRequestPriceValidation:
    def test_limit_no_price(self):
        with pytest.raises(ValidationError, match=r"LIMIT.*price"):
            OrderRequest(**_req(order_type="LIMIT", price=None))

    def test_stop_limit_no_price(self):
        with pytest.raises(ValidationError, match=r"STOP_LIMIT.*price"):
            OrderRequest(**_req(order_type="STOP_LIMIT", price=None, stop_price=41000.0))

    def test_stop_limit_no_stop_price(self):
        with pytest.raises(ValidationError, match=r"STOP_LIMIT.*stop_price"):
            OrderRequest(**_req(order_type="STOP_LIMIT", price=42000.0, stop_price=None))

    def test_stop_market_no_stop_price(self):
        with pytest.raises(ValidationError, match=r"STOP_MARKET.*stop_price"):
            OrderRequest(**_req(order_type="STOP_MARKET", price=None, stop_price=None))


class TestOrderRequestFieldValidation:
    def test_zero_quantity(self):
        with pytest.raises(ValidationError):
            OrderRequest(**_req(quantity=0))

    def test_negative_quantity(self):
        with pytest.raises(ValidationError):
            OrderRequest(**_req(quantity=-1.0))

    def test_empty_symbol(self):
        with pytest.raises(ValidationError):
            OrderRequest(**_req(symbol=""))

    def test_empty_proposal_id(self):
        with pytest.raises(ValidationError):
            OrderRequest(**_req(proposal_id=""))

    def test_zero_price(self):
        with pytest.raises(ValidationError):
            OrderRequest(**_req(price=0))

    def test_negative_price(self):
        with pytest.raises(ValidationError):
            OrderRequest(**_req(price=-100.0))


class TestOrderRequestSerialization:
    def test_json_round_trip(self):
        original = OrderRequest(**_req())
        restored = OrderRequest.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_dict_round_trip(self):
        original = OrderRequest(**_req())
        restored = OrderRequest(**original.model_dump())
        assert restored == original


# ---- Order ----


class TestOrderValid:
    def test_pending_order(self):
        o = Order(**_order())
        assert o.status == OrderStatus.PENDING
        assert o.filled_quantity == 0.0

    def test_filled_order(self):
        o = Order(
            **_order(
                status="FILLED",
                filled_quantity=0.5,
                average_fill_price=42510.0,
                exchange_order_id="EX-123",
            )
        )
        assert o.is_terminal
        assert o.remaining_quantity == 0.0

    def test_partial_fill(self):
        o = Order(**_order(status="PARTIAL", filled_quantity=0.3))
        assert not o.is_terminal
        assert o.remaining_quantity == pytest.approx(0.2)


class TestOrderFillInvariant:
    def test_overfill_rejected(self):
        with pytest.raises(ValidationError, match=r"filled_quantity.*exceeds"):
            Order(**_order(filled_quantity=0.6))  # quantity is 0.5

    def test_exact_fill_ok(self):
        o = Order(**_order(filled_quantity=0.5, status="FILLED"))
        assert o.remaining_quantity == 0.0

    def test_zero_fill_ok(self):
        o = Order(**_order(filled_quantity=0.0))
        assert o.remaining_quantity == 0.5


class TestOrderTerminal:
    @pytest.mark.parametrize("status", ["FILLED", "CANCELLED", "REJECTED", "EXPIRED"])
    def test_terminal(self, status):
        o = Order(**_order(status=status, filled_quantity=0.5 if status == "FILLED" else 0.0))
        assert o.is_terminal

    @pytest.mark.parametrize("status", ["PENDING", "SUBMITTED", "PARTIAL"])
    def test_non_terminal(self, status):
        o = Order(**_order(status=status))
        assert not o.is_terminal


class TestOrderSerialization:
    def test_json_round_trip(self):
        original = Order(**_order())
        restored = Order.model_validate_json(original.model_dump_json())
        assert restored == original
