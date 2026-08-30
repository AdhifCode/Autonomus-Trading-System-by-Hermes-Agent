"""Hermes Market Tools Module.

Provides read-only market data access tools for Hermes:
- get_market_state
- get_ohlcv
- get_orderbook

Hermes must never use these tools to execute orders or access credentials.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class MarketTools:
    """Read-only Market Data tools provider for Hermes."""

    def __init__(self, market_data_provider: Any | None = None) -> None:
        self.provider = market_data_provider

    def get_market_state(self, symbol: str) -> dict[str, Any]:
        """Fetch current market state summary for a symbol."""
        if self.provider is not None and hasattr(self.provider, "get_market_state"):
            state = self.provider.get_market_state(symbol)
            if hasattr(state, "model_dump"):
                return state.model_dump()  # type: ignore[no-any-return]
            return dict(state)

        # Fallback / default data contract response
        return {
            "symbol": symbol.upper(),
            "last_price": 68500.0,
            "bid": 68495.0,
            "ask": 68505.0,
            "spread": 10.0,
            "spread_pct": 0.000146,
            "volatility": 0.015,
            "volume_24h": 125000000.0,
            "is_stale": False,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> list[dict[str, Any]]:
        """Fetch historical candle series."""
        if self.provider is not None and hasattr(self.provider, "get_ohlcv"):
            return self.provider.get_ohlcv(symbol, timeframe=timeframe, limit=limit)  # type: ignore[no-any-return]

        now_ts = datetime.now(UTC).isoformat()
        return [
            {
                "timestamp": now_ts,
                "symbol": symbol.upper(),
                "open": 68000.0,
                "high": 68900.0,
                "low": 67800.0,
                "close": 68500.0,
                "volume": 1500.0,
            }
        ]

    def get_orderbook(self, symbol: str, depth: int = 20) -> dict[str, Any]:
        """Fetch orderbook snapshot."""
        if self.provider is not None and hasattr(self.provider, "get_orderbook"):
            return self.provider.get_orderbook(symbol, depth=depth)  # type: ignore[no-any-return]

        return {
            "symbol": symbol.upper(),
            "bids": [[68495.0, 1.5], [68490.0, 2.3]],
            "asks": [[68505.0, 1.2], [68510.0, 3.1]],
            "timestamp": datetime.now(UTC).isoformat(),
        }


__all__ = ["MarketTools"]
