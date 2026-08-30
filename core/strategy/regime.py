"""Market Regime Engine Module.

Classifies market state into explicit regime categories:
- BULL: Positive trend, high ADX trend strength, bullish momentum/structure
- BEAR: Negative trend, high ADX trend strength, bearish momentum/structure
- SIDEWAYS: Low trend strength (ADX < threshold, balanced momentum)
- HIGH_VOLATILITY: Volatility spike exceeding threshold
- LOW_VOLATILITY: Compressed volatility and low ADX

CRITICAL RULE (architecture §22):
ADX is used ONLY for trend STRENGTH, NOT trend direction.
ADX alone never determines BULL vs BEAR.

See implementation_spec.md §5 and architecture.md §22.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.domain.enums import MarketRegime


class RegimeInput(BaseModel):
    """Multi-factor inputs required for explicit market regime classification."""

    timestamp: datetime | None = None
    trend_direction: float = Field(
        default=0.0, description="+1.0 for bullish slope/cross, -1.0 for bearish, 0.0 for neutral"
    )
    trend_strength_adx: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Average Directional Index (trend strength ONLY)"
    )
    volatility: float = Field(
        default=0.0, ge=0.0, description="Standard deviation of log returns or normalized ATR"
    )
    liquidity_ratio: float = Field(
        default=1.0, ge=0.0, description="Current bar volume relative to 20-period moving average"
    )
    momentum_rsi: float = Field(
        default=50.0, ge=0.0, le=100.0, description="Relative Strength Index"
    )
    market_structure: str = Field(
        default="RANGING",
        description="Market structural pattern: HIGHER_HIGHS, LOWER_LOWS, or RANGING",
    )


class MarketRegimeEngine:
    """Market regime classifier using trend, ADX, volatility, liquidity, momentum, and structure."""

    def __init__(
        self,
        high_volatility_threshold: float = 0.025,  # 2.5% volatility threshold
        low_volatility_threshold: float = 0.005,  # 0.5% volatility threshold
        adx_trend_threshold: float = 25.0,  # ADX >= 25 indicates strong trend
        rsi_bullish_threshold: float = 52.0,
        rsi_bearish_threshold: float = 48.0,
    ) -> None:
        self.high_volatility_threshold = high_volatility_threshold
        self.low_volatility_threshold = low_volatility_threshold
        self.adx_trend_threshold = adx_trend_threshold
        self.rsi_bullish_threshold = rsi_bullish_threshold
        self.rsi_bearish_threshold = rsi_bearish_threshold

    def classify(self, inputs: RegimeInput) -> MarketRegime:
        """Classify market regime based on explicit multi-factor decision tree.

        1. HIGH_VOLATILITY: Volatility >= high_volatility_threshold
        2. LOW_VOLATILITY: Volatility <= low_volatility_threshold AND ADX < adx_trend_threshold
        3. BULL: ADX >= adx_trend_threshold AND (trend_direction > 0 OR HIGHER_HIGHS)
        4. BEAR: ADX >= adx_trend_threshold AND (trend_direction < 0 OR LOWER_LOWS)
        5. SIDEWAYS: ADX < adx_trend_threshold OR ambiguous direction
        """
        # Step 1: Volatility checks
        if inputs.volatility >= self.high_volatility_threshold:
            return MarketRegime.HIGH_VOLATILITY

        if (
            inputs.volatility <= self.low_volatility_threshold
            and inputs.trend_strength_adx < self.adx_trend_threshold
        ):
            return MarketRegime.LOW_VOLATILITY

        # Step 2: Strong trend classification (ADX = STRENGTH ONLY)
        if inputs.trend_strength_adx >= self.adx_trend_threshold:
            # Check direction indicators (trend_direction, market_structure, RSI)
            is_bullish = (
                inputs.trend_direction > 0
                or inputs.market_structure == "HIGHER_HIGHS"
                or (
                    inputs.trend_direction == 0
                    and inputs.momentum_rsi >= self.rsi_bullish_threshold
                )
            )
            is_bearish = (
                inputs.trend_direction < 0
                or inputs.market_structure == "LOWER_LOWS"
                or (
                    inputs.trend_direction == 0
                    and inputs.momentum_rsi <= self.rsi_bearish_threshold
                )
            )

            if is_bullish and not is_bearish:
                return MarketRegime.BULL
            if is_bearish and not is_bullish:
                return MarketRegime.BEAR

        # Step 3: Low trend strength or balanced momentum -> SIDEWAYS
        return MarketRegime.SIDEWAYS


__all__ = ["MarketRegimeEngine", "RegimeInput"]
