"""Tests for core.domain.market_state — MarketState, OHLCV, OrderBook models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.domain.market_state import (
    OHLCV,
    AccountInfo,
    MarketState,
    OrderBook,
    OrderBookEntry,
)

_NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


# ---- OHLCV ----


def _ohlcv(**kw):
    d = {
        "timestamp": _NOW.isoformat(),
        "open": 42000.0,
        "high": 43000.0,
        "low": 41500.0,
        "close": 42800.0,
        "volume": 1000.0,
    }
    d.update(kw)
    return d


class TestOHLCVValid:
    def test_basic(self):
        o = OHLCV(**_ohlcv())
        assert o.high == 43000.0

    def test_zero_volume(self):
        o = OHLCV(**_ohlcv(volume=0.0))
        assert o.volume == 0.0


class TestOHLCVInvariant:
    def test_high_below_low(self):
        with pytest.raises(ValidationError, match=r"high.*low"):
            OHLCV(**_ohlcv(high=41000.0, low=42000.0))

    def test_high_below_open(self):
        with pytest.raises(ValidationError, match=r"high.*open"):
            OHLCV(**_ohlcv(open=44000.0, high=43000.0))

    def test_high_below_close(self):
        with pytest.raises(ValidationError, match=r"high.*close"):
            OHLCV(**_ohlcv(close=44000.0, high=43000.0))

    def test_low_above_open(self):
        with pytest.raises(ValidationError, match=r"low.*open"):
            OHLCV(**_ohlcv(open=41000.0, low=41500.0))

    def test_low_above_close(self):
        with pytest.raises(ValidationError, match=r"low.*close"):
            OHLCV(**_ohlcv(close=41000.0, low=41500.0))

    def test_equal_ohlc_valid(self):
        """Doji candle: O=H=L=C."""
        o = OHLCV(**_ohlcv(open=42000.0, high=42000.0, low=42000.0, close=42000.0))
        assert o.open == o.high == o.low == o.close


class TestOHLCVInvalid:
    def test_zero_price(self):
        with pytest.raises(ValidationError):
            OHLCV(**_ohlcv(open=0))

    def test_negative_price(self):
        with pytest.raises(ValidationError):
            OHLCV(**_ohlcv(close=-1.0))

    def test_negative_volume(self):
        with pytest.raises(ValidationError):
            OHLCV(**_ohlcv(volume=-100))


# ---- OrderBookEntry ----


class TestOrderBookEntry:
    def test_valid(self):
        e = OrderBookEntry(price=42500.0, quantity=1.5)
        assert e.price == 42500.0

    def test_zero_price(self):
        with pytest.raises(ValidationError):
            OrderBookEntry(price=0, quantity=1.0)

    def test_zero_quantity(self):
        with pytest.raises(ValidationError):
            OrderBookEntry(price=100.0, quantity=0)


# ---- OrderBook ----


class TestOrderBook:
    def test_basic(self):
        ob = OrderBook(
            bids=[OrderBookEntry(price=42490.0, quantity=1.0)],
            asks=[OrderBookEntry(price=42510.0, quantity=0.5)],
            timestamp=_NOW,
        )
        assert ob.best_bid == 42490.0
        assert ob.best_ask == 42510.0
        assert ob.spread == pytest.approx(20.0)

    def test_empty_book(self):
        ob = OrderBook(bids=[], asks=[], timestamp=_NOW)
        assert ob.best_bid is None
        assert ob.best_ask is None
        assert ob.spread is None
        assert ob.spread_pct is None

    def test_spread_pct(self):
        ob = OrderBook(
            bids=[OrderBookEntry(price=100.0, quantity=1.0)],
            asks=[OrderBookEntry(price=101.0, quantity=1.0)],
            timestamp=_NOW,
        )
        mid = 100.5
        expected = 1.0 / mid
        assert ob.spread_pct == pytest.approx(expected)


# ---- AccountInfo ----


class TestAccountInfo:
    def test_valid(self):
        ai = AccountInfo(
            balance=100000.0,
            equity=102000.0,
            available_margin=80000.0,
            unrealized_pnl=2000.0,
            timestamp=_NOW,
        )
        assert ai.balance == 100000.0

    def test_serialization(self):
        original = AccountInfo(
            balance=100000.0,
            equity=102000.0,
            available_margin=80000.0,
            unrealized_pnl=2000.0,
            timestamp=_NOW,
        )
        restored = AccountInfo.model_validate_json(original.model_dump_json())
        assert restored == original


# ---- MarketState ----


def _market(**kw):
    d = {
        "symbol": "BTCUSDT",
        "price": 42500.0,
        "bid": 42490.0,
        "ask": 42510.0,
        "spread": 20.0,
        "volume_24h": 5000000.0,
        "timestamp": _NOW.isoformat(),
        "data_age_seconds": 1.5,
    }
    d.update(kw)
    return d


class TestMarketStateValid:
    def test_basic(self):
        ms = MarketState(**_market())
        assert ms.symbol == "BTCUSDT"
        assert ms.order_book is None

    def test_with_ohlcv(self):
        ms = MarketState(**_market(ohlcv=[_ohlcv()]))
        assert len(ms.ohlcv) == 1


class TestMarketStateBidAsk:
    def test_ask_below_bid_rejected(self):
        with pytest.raises(ValidationError, match=r"ask.*bid"):
            MarketState(**_market(bid=42510.0, ask=42490.0))

    def test_equal_bid_ask(self):
        ms = MarketState(**_market(bid=42500.0, ask=42500.0, spread=0.0))
        assert ms.bid == ms.ask


class TestMarketStateInvalid:
    def test_zero_price(self):
        with pytest.raises(ValidationError):
            MarketState(**_market(price=0))

    def test_empty_symbol(self):
        with pytest.raises(ValidationError):
            MarketState(**_market(symbol=""))

    def test_negative_spread(self):
        with pytest.raises(ValidationError):
            MarketState(**_market(spread=-1.0))

    def test_negative_volume(self):
        with pytest.raises(ValidationError):
            MarketState(**_market(volume_24h=-100))

    def test_negative_data_age(self):
        with pytest.raises(ValidationError):
            MarketState(**_market(data_age_seconds=-1.0))


class TestMarketStateSerialization:
    def test_json_round_trip(self):
        original = MarketState(**_market())
        restored = MarketState.model_validate_json(original.model_dump_json())
        assert restored == original
