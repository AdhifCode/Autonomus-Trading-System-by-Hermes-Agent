"""Tests for core.domain.trade_proposal — TradeProposal model.

Covers valid/invalid construction, boundaries, price logic, enums, serialization.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.domain.enums import OrderSide, OrderType
from core.domain.trade_proposal import (
    EntrySpec,
    PositionSizeSpec,
    StopLossSpec,
    TakeProfitSpec,
    TradeProposal,
)

_NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _long(**kw):
    d = {
        "proposal_id": "PRP-20260828-000001",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "strategy_id": "breakout",
        "strategy_version": "2.1",
        "model_version": "claude-3.5-sonnet",
        "thesis": "Breakout above resistance with volume confirmation",
        "entry": {"price": 42500.0, "order_type": "LIMIT"},
        "stop_loss": {"price": 41000.0},
        "take_profit": {"price": 44000.0},
        "position_size": {"requested_pct": 0.05},
        "market_regime": "BULL",
        "invalidation_conditions": ["Price drops below 40500"],
        "evidence": ["Volume spike above 2x average"],
        "uncertainty": ["Macro event risk"],
        "llm_confidence": 0.75,
        "created_at": _NOW.isoformat(),
    }
    d.update(kw)
    return d


def _short(**kw):
    d = {
        "proposal_id": "PRP-20260828-000002",
        "symbol": "ETHUSDT",
        "side": "SELL",
        "strategy_id": "mean_rev",
        "strategy_version": "1.0",
        "model_version": "gpt-4o",
        "thesis": "Overbought RSI with bearish divergence pattern",
        "entry": {"price": 3400.0, "order_type": "MARKET"},
        "stop_loss": {"price": 3600.0},
        "take_profit": {"price": 3200.0},
        "position_size": {"requested_pct": 0.03},
        "market_regime": "BEAR",
        "invalidation_conditions": ["Price breaks above 3700"],
        "evidence": ["RSI > 80"],
        "uncertainty": [],
        "llm_confidence": 0.60,
        "created_at": _NOW.isoformat(),
    }
    d.update(kw)
    return d


class TestEntrySpec:
    def test_valid(self):
        e = EntrySpec(price=100.0, order_type=OrderType.LIMIT)
        assert e.price == 100.0

    def test_zero_price(self):
        with pytest.raises(ValidationError):
            EntrySpec(price=0, order_type=OrderType.MARKET)

    def test_negative_price(self):
        with pytest.raises(ValidationError):
            EntrySpec(price=-1.0, order_type=OrderType.LIMIT)

    def test_invalid_order_type(self):
        with pytest.raises(ValidationError):
            EntrySpec(price=100.0, order_type="TWAP")  # type: ignore[arg-type]


class TestStopLossSpec:
    def test_valid(self):
        assert StopLossSpec(price=41000.0).price == 41000.0

    def test_zero(self):
        with pytest.raises(ValidationError):
            StopLossSpec(price=0)

    def test_negative(self):
        with pytest.raises(ValidationError):
            StopLossSpec(price=-500.0)


class TestTakeProfitSpec:
    def test_valid(self):
        assert TakeProfitSpec(price=50000.0).price == 50000.0

    def test_zero(self):
        with pytest.raises(ValidationError):
            TakeProfitSpec(price=0)


class TestPositionSizeSpec:
    def test_valid(self):
        assert PositionSizeSpec(requested_pct=0.05).requested_pct == 0.05

    def test_zero_rejected(self):
        with pytest.raises(ValidationError):
            PositionSizeSpec(requested_pct=0.0)

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            PositionSizeSpec(requested_pct=-0.1)

    def test_max_boundary(self):
        assert PositionSizeSpec(requested_pct=1.0).requested_pct == 1.0

    def test_over_max(self):
        with pytest.raises(ValidationError):
            PositionSizeSpec(requested_pct=1.01)

    def test_tiny(self):
        assert PositionSizeSpec(requested_pct=0.001).requested_pct == 0.001


class TestTradeProposalValid:
    def test_valid_long(self):
        p = TradeProposal(**_long())
        assert p.side == OrderSide.BUY
        assert p.entry.price == 42500.0

    def test_valid_short(self):
        p = TradeProposal(**_short())
        assert p.side == OrderSide.SELL
        assert p.stop_loss.price > p.entry.price

    def test_empty_uncertainty(self):
        p = TradeProposal(**_long(uncertainty=[]))
        assert p.uncertainty == []


class TestProposalId:
    def test_valid(self):
        p = TradeProposal(**_long(proposal_id="PRP-20260101-000001"))
        assert p.proposal_id == "PRP-20260101-000001"

    @pytest.mark.parametrize(
        "bad_id",
        [
            "PRP-2026-000001",
            "PRP-20260828-00001",
            "TRD-20260828-000001",
            "PRP20260828000001",
            "",
            "prp-20260828-000001",
        ],
    )
    def test_invalid_format(self, bad_id):
        with pytest.raises(ValidationError):
            TradeProposal(**_long(proposal_id=bad_id))


class TestPriceLogic:
    def test_long_sl_above_entry(self):
        with pytest.raises(ValidationError, match="stop-loss"):
            TradeProposal(**_long(stop_loss={"price": 43000.0}))

    def test_long_sl_equal_entry(self):
        with pytest.raises(ValidationError, match="stop-loss"):
            TradeProposal(**_long(stop_loss={"price": 42500.0}))

    def test_long_tp_below_entry(self):
        with pytest.raises(ValidationError, match="take-profit"):
            TradeProposal(**_long(take_profit={"price": 41000.0}))

    def test_long_tp_equal_entry(self):
        with pytest.raises(ValidationError, match="take-profit"):
            TradeProposal(**_long(take_profit={"price": 42500.0}))

    def test_short_sl_below_entry(self):
        with pytest.raises(ValidationError, match="stop-loss"):
            TradeProposal(**_short(stop_loss={"price": 3300.0}))

    def test_short_sl_equal_entry(self):
        with pytest.raises(ValidationError, match="stop-loss"):
            TradeProposal(**_short(stop_loss={"price": 3400.0}))

    def test_short_tp_above_entry(self):
        with pytest.raises(ValidationError, match="take-profit"):
            TradeProposal(**_short(take_profit={"price": 3500.0}))

    def test_short_tp_equal_entry(self):
        with pytest.raises(ValidationError, match="take-profit"):
            TradeProposal(**_short(take_profit={"price": 3400.0}))


class TestLLMConfidence:
    def test_zero(self):
        assert TradeProposal(**_long(llm_confidence=0.0)).llm_confidence == 0.0

    def test_one(self):
        assert TradeProposal(**_long(llm_confidence=1.0)).llm_confidence == 1.0

    def test_below_zero(self):
        with pytest.raises(ValidationError):
            TradeProposal(**_long(llm_confidence=-0.01))

    def test_above_one(self):
        with pytest.raises(ValidationError):
            TradeProposal(**_long(llm_confidence=1.01))

    def test_metadata_only_documented(self):
        desc = TradeProposal.model_fields["llm_confidence"].description or ""
        assert "METADATA" in desc.upper()


class TestMissingFields:
    @pytest.mark.parametrize(
        "field",
        [
            "proposal_id",
            "symbol",
            "side",
            "strategy_id",
            "strategy_version",
            "model_version",
            "thesis",
            "entry",
            "stop_loss",
            "take_profit",
            "position_size",
            "market_regime",
            "invalidation_conditions",
            "evidence",
            "llm_confidence",
            "created_at",
        ],
    )
    def test_missing(self, field):
        data = _long()
        del data[field]
        with pytest.raises(ValidationError):
            TradeProposal(**data)


class TestInvalidEnums:
    def test_invalid_side(self):
        with pytest.raises(ValidationError):
            TradeProposal(**_long(side="HOLD"))

    def test_invalid_regime(self):
        with pytest.raises(ValidationError):
            TradeProposal(**_long(market_regime="CRASH"))

    def test_invalid_entry_type(self):
        with pytest.raises(ValidationError):
            TradeProposal(**_long(entry={"price": 42500.0, "order_type": "TWAP"}))


class TestFieldValidation:
    def test_empty_symbol(self):
        with pytest.raises(ValidationError):
            TradeProposal(**_long(symbol=""))

    def test_short_thesis(self):
        with pytest.raises(ValidationError):
            TradeProposal(**_long(thesis="Short"))

    def test_thesis_10_chars(self):
        p = TradeProposal(**_long(thesis="1234567890"))
        assert len(p.thesis) == 10

    def test_empty_invalidation(self):
        with pytest.raises(ValidationError):
            TradeProposal(**_long(invalidation_conditions=[]))

    def test_empty_evidence(self):
        with pytest.raises(ValidationError):
            TradeProposal(**_long(evidence=[]))


class TestSerialization:
    def test_json_round_trip(self):
        original = TradeProposal(**_long())
        restored = TradeProposal.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_dict_round_trip(self):
        original = TradeProposal(**_long())
        restored = TradeProposal(**original.model_dump())
        assert restored == original

    def test_all_keys_present(self):
        d = TradeProposal(**_long()).model_dump()
        expected = {
            "proposal_id",
            "symbol",
            "side",
            "strategy_id",
            "strategy_version",
            "model_version",
            "thesis",
            "entry",
            "stop_loss",
            "take_profit",
            "position_size",
            "market_regime",
            "invalidation_conditions",
            "evidence",
            "uncertainty",
            "llm_confidence",
            "created_at",
        }
        assert set(d.keys()) == expected

    def test_nested_serialization(self):
        d = TradeProposal(**_long()).model_dump()
        assert isinstance(d["entry"], dict)
        assert d["entry"]["price"] == 42500.0

    def test_json_schema(self):
        schema = TradeProposal.model_json_schema()
        assert "properties" in schema
        assert "proposal_id" in schema["properties"]
