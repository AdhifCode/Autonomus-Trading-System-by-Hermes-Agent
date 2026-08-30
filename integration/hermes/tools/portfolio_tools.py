"""Hermes Portfolio Tools Module.

Provides READ-ONLY portfolio state access for Hermes:
- get_portfolio
- get_positions
- get_pnl

INVARIANT (architecture §31):
Hermes must NEVER be treated as the source of truth for portfolio state.
All values returned here are read-only views provided by the system.
Hermes cannot modify portfolio, positions, or balances.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class PortfolioTools:
    """Read-only Portfolio metrics provider for Hermes."""

    def __init__(self, portfolio_provider: Any | None = None) -> None:
        self.provider = portfolio_provider

    def get_portfolio(self) -> dict[str, Any]:
        """Fetch summary portfolio accounting state (read-only)."""
        if self.provider is not None and hasattr(self.provider, "get_portfolio_summary"):
            return self.provider.get_portfolio_summary()  # type: ignore[no-any-return]

        return {
            "total_equity": 100000.0,
            "cash_balance": 85000.0,
            "used_margin": 15000.0,
            "available_margin": 85000.0,
            "unrealized_pnl": 500.0,
            "daily_pnl": 250.0,
            "weekly_pnl": 1200.0,
            "peak_equity": 102000.0,
            "current_drawdown": 0.0196,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_positions(self) -> list[dict[str, Any]]:
        """Fetch active portfolio positions (read-only)."""
        if self.provider is not None and hasattr(self.provider, "get_open_positions"):
            positions = self.provider.get_open_positions()
            return [p.model_dump() if hasattr(p, "model_dump") else dict(p) for p in positions]

        return [
            {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "quantity": 0.25,
                "entry_price": 67800.0,
                "current_price": 68500.0,
                "unrealized_pnl": 175.0,
                "leverage": 1.0,
            }
        ]

    def get_pnl(self) -> dict[str, Any]:
        """Fetch historical PnL metrics summary (read-only)."""
        return {
            "daily_realized_pnl": 250.0,
            "weekly_realized_pnl": 1200.0,
            "cumulative_pnl": 5400.0,
            "win_rate": 0.65,
            "profit_factor": 1.85,
            "timestamp": datetime.now(UTC).isoformat(),
        }


__all__ = ["PortfolioTools"]
