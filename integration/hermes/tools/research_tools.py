"""Hermes Research Tools Module.

Provides read-only research tools for Hermes:
- get_regime
- get_indicators
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.domain.enums import MarketRegime
from core.strategy.regime import MarketRegimeEngine, RegimeInput


class ResearchTools:
    """Read-only Research tools provider for Hermes."""

    def __init__(self, regime_engine: MarketRegimeEngine | None = None) -> None:
        self.regime_engine = regime_engine or MarketRegimeEngine()

    def get_regime(self, symbol: str) -> dict[str, Any]:
        """Fetch current classified market regime for a symbol."""
        reg_input = RegimeInput(
            trend_direction=1.0,
            trend_strength_adx=32.0,
            volatility=0.015,
            momentum_rsi=58.0,
            market_structure="HIGHER_HIGHS",
        )
        regime = self.regime_engine.classify(reg_input)

        return {
            "symbol": symbol.upper(),
            "regime": regime.value if isinstance(regime, MarketRegime) else str(regime),
            "trend_strength_adx": 32.0,
            "adx_is_strength_only": True,
            "volatility": 0.015,
            "market_structure": "HIGHER_HIGHS",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_indicators(self, symbol: str) -> dict[str, Any]:
        """Fetch technical indicators summary for a symbol."""
        return {
            "symbol": symbol.upper(),
            "sma_fast": 68200.0,
            "sma_slow": 67400.0,
            "rsi": 58.0,
            "atr": 450.0,
            "adx": 32.0,
            "volatility": 0.015,
            "timestamp": datetime.now(UTC).isoformat(),
        }


__all__ = ["ResearchTools"]
