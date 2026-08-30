"""Strategy Interface Module.

Defines the standard base interface for trading strategies:
- Evaluates signals given historical market bar series and features
- Respects strategy version configuration and applicable market regimes
- Generates valid TradeProposals or signals for execution

See implementation_spec.md §15.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING

from core.domain.enums import MarketRegime, OrderSide
from core.domain.strategy import StrategyVersion

if TYPE_CHECKING:
    from data.features.generator import MarketFeatures
    from data.validation.checker import Candle


class BaseStrategy(ABC):
    """Abstract Base Class for all trading strategy implementations."""

    def __init__(self, version: StrategyVersion) -> None:
        self.version = version

    @property
    def strategy_id(self) -> str:
        """Return strategy identifier."""
        return self.version.strategy_id

    @property
    def qualified_name(self) -> str:
        """Return 'strategy_id:version'."""
        return self.version.qualified_name

    def is_regime_allowed(self, current_regime: MarketRegime) -> bool:
        """Check if strategy is allowed to trade in the given market regime."""
        if not self.version.applicable_regimes:
            return True  # If unspecified, allowed in all regimes
        return current_regime in self.version.applicable_regimes

    @abstractmethod
    def generate_signal(
        self,
        candles: Sequence[Candle],
        features: Sequence[MarketFeatures],
        t: int,
    ) -> OrderSide | None:
        """Evaluate market data up to bar `t` and return an OrderSide signal or None."""
        pass


__all__ = ["BaseStrategy"]
