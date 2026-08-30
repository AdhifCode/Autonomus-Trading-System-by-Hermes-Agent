"""Market state domain models.

See implementation_spec.md §2.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class OHLCV(BaseModel):
    """Single OHLCV candlestick bar."""

    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_hloc(self) -> OHLCV:
        """High must be >= open, close, low. Low must be <= open, close, high."""
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) < low ({self.low})")
        if self.high < self.open:
            raise ValueError(f"high ({self.high}) < open ({self.open})")
        if self.high < self.close:
            raise ValueError(f"high ({self.high}) < close ({self.close})")
        if self.low > self.open:
            raise ValueError(f"low ({self.low}) > open ({self.open})")
        if self.low > self.close:
            raise ValueError(f"low ({self.low}) > close ({self.close})")
        return self


class OrderBookEntry(BaseModel):
    """Single price level in the order book."""

    price: float = Field(gt=0)
    quantity: float = Field(gt=0)


class OrderBook(BaseModel):
    """Exchange order book snapshot."""

    bids: list[OrderBookEntry]
    asks: list[OrderBookEntry]
    timestamp: datetime

    @property
    def best_bid(self) -> float | None:
        """Return best (highest) bid price."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        """Return best (lowest) ask price."""
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> float | None:
        """Return bid-ask spread."""
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_ask - self.best_bid
        return None

    @property
    def spread_pct(self) -> float | None:
        """Return spread as percentage of mid-price."""
        if self.best_bid is not None and self.best_ask is not None:
            mid = (self.best_bid + self.best_ask) / 2
            if mid > 0:
                return (self.best_ask - self.best_bid) / mid
        return None


class AccountInfo(BaseModel):
    """Exchange account information returned by ExchangeAdapter.get_account().

    See implementation_spec.md §2 (ambiguity #12).
    """

    balance: float
    equity: float
    available_margin: float
    unrealized_pnl: float
    timestamp: datetime


class MarketState(BaseModel):
    """Current market state for a symbol."""

    symbol: str = Field(min_length=1)
    price: float = Field(gt=0)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    spread: float = Field(ge=0)
    volume_24h: float = Field(ge=0)
    ohlcv: list[OHLCV] = Field(default_factory=list)
    order_book: OrderBook | None = None
    timestamp: datetime
    data_age_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_bid_ask(self) -> MarketState:
        """Ask must be >= bid."""
        if self.ask < self.bid:
            raise ValueError(f"ask ({self.ask}) < bid ({self.bid})")
        return self
