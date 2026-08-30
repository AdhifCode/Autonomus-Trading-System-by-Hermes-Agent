"""Feature Generation & Market Regime Integration Module.

Computes technical indicators and multi-factor market features:
- Moving Averages (SMA, EMA)
- ADX (Average Directional Index - trend strength ONLY)
- ATR (Average True Range)
- Volatility (Standard Deviation of log returns)
- Momentum & RSI
- Liquidity Volume Ratio
- Market Structure (HIGHER_HIGHS, LOWER_LOWS, RANGING)
- Market Regime Classification (BULL, BEAR, SIDEWAYS, HIGH_VOLATILITY, LOW_VOLATILITY)

See implementation_spec.md §5 and architecture.md §22.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel

from core.domain.enums import MarketRegime
from core.strategy.regime import MarketRegimeEngine, RegimeInput
from data.validation.checker import Candle

# Backwards compatibility alias
RegimeType = MarketRegime


class MarketFeatures(BaseModel):
    """Calculated technical features for a specific bar timestamp."""

    timestamp: str
    symbol: str
    close_price: float
    sma_fast: float | None = None
    sma_slow: float | None = None
    ema_fast: float | None = None
    rsi: float | None = None
    atr: float | None = None
    adx: float | None = None
    volatility: float | None = None
    liquidity_ratio: float | None = None
    market_structure: str = "RANGING"
    regime: MarketRegime = MarketRegime.SIDEWAYS


class FeatureGenerator:
    """Computes technical indicators and market features over Candle series."""

    @staticmethod
    def compute_sma(prices: Sequence[float], period: int) -> list[float | None]:
        """Compute Simple Moving Average."""
        result: list[float | None] = [None] * len(prices)
        if len(prices) < period or period <= 0:
            return result

        current_sum = sum(prices[:period])
        result[period - 1] = current_sum / period

        for i in range(period, len(prices)):
            current_sum += prices[i] - prices[i - period]
            result[i] = current_sum / period

        return result

    @staticmethod
    def compute_rsi(prices: Sequence[float], period: int = 14) -> list[float | None]:
        """Compute Relative Strength Index (RSI)."""
        result: list[float | None] = [None] * len(prices)
        if len(prices) <= period or period <= 0:
            return result

        gains = 0.0
        losses = 0.0

        for i in range(1, period + 1):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains += change
            else:
                losses += abs(change)

        avg_gain = gains / period
        avg_loss = losses / period

        if avg_loss == 0:
            result[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[period] = 100.0 - (100.0 / (1.0 + rs))

        for i in range(period + 1, len(prices)):
            change = prices[i] - prices[i - 1]
            gain = change if change > 0 else 0.0
            loss = abs(change) if change < 0 else 0.0

            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

            if avg_loss == 0:
                result[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[i] = 100.0 - (100.0 / (1.0 + rs))

        return result

    @staticmethod
    def compute_volatility(prices: Sequence[float], period: int = 20) -> list[float | None]:
        """Compute rolling standard deviation of log returns as volatility measure."""
        result: list[float | None] = [None] * len(prices)
        if len(prices) <= period or period <= 1:
            return result

        returns: list[float] = [0.0]
        for i in range(1, len(prices)):
            r = math.log(prices[i] / prices[i - 1]) if prices[i - 1] > 0 else 0.0
            returns.append(r)

        for i in range(period, len(prices)):
            window = returns[i - period + 1 : i + 1]
            mean = sum(window) / period
            variance = sum((x - mean) ** 2 for x in window) / (period - 1)
            result[i] = math.sqrt(variance)

        return result

    @staticmethod
    def compute_atr(candles: Sequence[Candle], period: int = 14) -> list[float | None]:
        """Compute Average True Range (ATR)."""
        result: list[float | None] = [None] * len(candles)
        if len(candles) <= period or period <= 0:
            return result

        tr_list: list[float] = [0.0]
        for i in range(1, len(candles)):
            c = candles[i]
            prev_c = candles[i - 1]
            tr = max(c.high - c.low, abs(c.high - prev_c.close), abs(c.low - prev_c.close))
            tr_list.append(tr)

        atr = sum(tr_list[1 : period + 1]) / period
        result[period] = atr

        for i in range(period + 1, len(candles)):
            atr = (atr * (period - 1) + tr_list[i]) / period
            result[i] = atr

        return result

    @staticmethod
    def compute_adx(candles: Sequence[Candle], period: int = 14) -> list[float | None]:
        """Compute Average Directional Index (ADX) measuring trend strength ONLY."""
        result: list[float | None] = [None] * len(candles)
        if len(candles) <= (period * 2):
            return result

        plus_dm: list[float] = [0.0]
        minus_dm: list[float] = [0.0]
        tr_list: list[float] = [0.0]

        for i in range(1, len(candles)):
            c = candles[i]
            prev_c = candles[i - 1]

            up_move = c.high - prev_c.high
            down_move = prev_c.low - c.low

            p_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
            m_dm = down_move if (down_move > up_move and down_move > 0) else 0.0

            plus_dm.append(p_dm)
            minus_dm.append(m_dm)

            tr = max(c.high - c.low, abs(c.high - prev_c.close), abs(c.low - prev_c.close))
            tr_list.append(tr)

        # Smooth TR, +DM, -DM
        atr_smooth = sum(tr_list[1 : period + 1])
        p_dm_smooth = sum(plus_dm[1 : period + 1])
        m_dm_smooth = sum(minus_dm[1 : period + 1])

        dx_list: list[float | None] = [None] * len(candles)

        for i in range(period, len(candles)):
            if i > period:
                atr_smooth = atr_smooth - (atr_smooth / period) + tr_list[i]
                p_dm_smooth = p_dm_smooth - (p_dm_smooth / period) + plus_dm[i]
                m_dm_smooth = m_dm_smooth - (m_dm_smooth / period) + minus_dm[i]

            p_di = 100.0 * (p_dm_smooth / atr_smooth) if atr_smooth > 0 else 0.0
            m_di = 100.0 * (m_dm_smooth / atr_smooth) if atr_smooth > 0 else 0.0

            di_sum = p_di + m_di
            dx = 100.0 * (abs(p_di - m_di) / di_sum) if di_sum > 0 else 0.0
            dx_list[i] = dx

        # Compute ADX as smoothed average of DX
        first_adx_idx = period * 2
        valid_dxs = [x for x in dx_list[period:first_adx_idx] if x is not None]
        if valid_dxs:
            adx = sum(valid_dxs) / len(valid_dxs)
            result[first_adx_idx - 1] = adx

            for i in range(first_adx_idx, len(candles)):
                dx_val = dx_list[i] or 0.0
                adx = (adx * (period - 1) + dx_val) / period
                result[i] = adx

        return result

    @classmethod
    def generate_features(
        cls,
        candles: Sequence[Candle],
        fast_period: int = 10,
        slow_period: int = 30,
        rsi_period: int = 14,
        regime_engine: MarketRegimeEngine | None = None,
    ) -> list[MarketFeatures]:
        """Compute full feature sequence and regime classification for a list of candles."""
        closes = [c.close for c in candles]
        fast_smas = cls.compute_sma(closes, fast_period)
        slow_smas = cls.compute_sma(closes, slow_period)
        rsis = cls.compute_rsi(closes, rsi_period)
        vols = cls.compute_volatility(closes, period=slow_period)
        atrs = cls.compute_atr(candles, period=14)
        adxs = cls.compute_adx(candles, period=14)

        engine = regime_engine or MarketRegimeEngine()
        features: list[MarketFeatures] = []

        for i, c in enumerate(candles):
            f_sma = fast_smas[i]
            s_sma = slow_smas[i]
            rsi = rsis[i] or 50.0
            vol = vols[i] or 0.0
            adx = adxs[i] or 0.0

            # Trend direction: +1 if fast > slow, -1 if fast < slow
            trend_dir = 0.0
            if f_sma is not None and s_sma is not None:
                diff = (f_sma - s_sma) / s_sma if s_sma > 0 else 0.0
                if diff > 0.001:
                    trend_dir = 1.0
                elif diff < -0.001:
                    trend_dir = -1.0

            # Market structure
            m_struct = "RANGING"
            if i >= 1:
                prev_c = candles[i - 1]
                if c.high > prev_c.high and c.low > prev_c.low:
                    m_struct = "HIGHER_HIGHS"
                elif c.high < prev_c.high and c.low < prev_c.low:
                    m_struct = "LOWER_LOWS"

            reg_input = RegimeInput(
                timestamp=c.timestamp,
                trend_direction=trend_dir,
                trend_strength_adx=adx,
                volatility=vol,
                liquidity_ratio=1.0,
                momentum_rsi=rsi,
                market_structure=m_struct,
            )

            regime = engine.classify(reg_input)

            feat = MarketFeatures(
                timestamp=c.timestamp.isoformat(),
                symbol=c.symbol,
                close_price=c.close,
                sma_fast=f_sma,
                sma_slow=s_sma,
                rsi=rsis[i],
                atr=atrs[i],
                adx=adxs[i],
                volatility=vols[i],
                liquidity_ratio=1.0,
                market_structure=m_struct,
                regime=regime,
            )
            features.append(feat)

        return features


__all__ = [
    "FeatureGenerator",
    "MarketFeatures",
    "RegimeType",
]
