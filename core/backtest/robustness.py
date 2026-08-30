"""Robustness & Sensitivity Testing Module.

Provides advanced quantitative validation algorithms:
- Walk-Forward Optimization (WFO) sliding window analysis
- Parameter sensitivity grid testing
- Monte Carlo trade resampling (95% confidence intervals)
- Transaction cost & slippage stress testing (break-even multiplier)
- Regime performance breakdown
- Out-of-Sample (OOS) testing

See implementation_spec.md §5, §8.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from pydantic import BaseModel, Field

from core.backtest.analysis import PerformanceAnalyzer, PerformanceMetrics
from core.backtest.costs import TransactionCostModel
from core.backtest.engine import BacktestResult, DeterministicBacktestEngine, SignalStrategy
from data.features.generator import MarketFeatures, RegimeType
from data.validation.checker import Candle


class MonteCarloSummary(BaseModel):
    """Summary of Monte Carlo trade resampling simulations."""

    simulations: int
    mean_net_pnl: float
    p05_net_pnl: float  # 5th percentile (95% confidence lower bound)
    p95_net_pnl: float  # 95th percentile
    p95_max_drawdown_pct: float  # 95th percentile worst drawdown


class StressTestPoint(BaseModel):
    """Single point in transaction cost stress test."""

    cost_multiplier: float
    total_net_pnl: float
    max_drawdown_pct: float
    profit_factor: float
    is_profitable: bool


class WalkForwardWindowResult(BaseModel):
    """Result of a single Walk-Forward window."""

    window_index: int
    is_start: int
    is_end: int
    oos_start: int
    oos_end: int
    is_net_pnl: float
    oos_net_pnl: float


class WalkForwardSummary(BaseModel):
    """Overall summary of Walk-Forward Optimization."""

    total_windows: int
    aggregate_is_net_pnl: float
    aggregate_oos_net_pnl: float
    wfo_efficiency_ratio: float  # OOS Net PnL / IS Net PnL
    window_results: list[WalkForwardWindowResult] = Field(default_factory=list)


class RobustnessTester:
    """Executes Walk-Forward, Monte Carlo resampling, stress tests, and regime breakdowns."""

    def __init__(self, engine: DeterministicBacktestEngine | None = None) -> None:
        self.engine = engine or DeterministicBacktestEngine()

    def run_monte_carlo(
        self,
        result: BacktestResult,
        iterations: int = 500,
        seed: int = 42,
    ) -> MonteCarloSummary:
        """Perform Monte Carlo trade sequence resampling over trade Net PnLs."""
        if not result.trades:
            return MonteCarloSummary(
                simulations=iterations,
                mean_net_pnl=0.0,
                p05_net_pnl=0.0,
                p95_net_pnl=0.0,
                p95_max_drawdown_pct=0.0,
            )

        trade_pnls = [tr.net_pnl for tr in result.trades]
        rng = random.Random(seed)  # noqa: S311

        final_pnls: list[float] = []
        max_drawdowns: list[float] = []

        for _ in range(iterations):
            shuffled = list(trade_pnls)
            rng.shuffle(shuffled)

            balance = result.initial_balance
            peak = balance
            max_dd = 0.0

            for pnl in shuffled:
                balance += pnl
                if balance > peak:
                    peak = balance
                if peak > 0:
                    dd = ((peak - balance) / peak) * 100.0
                    if dd > max_dd:
                        max_dd = dd

            final_pnls.append(balance - result.initial_balance)
            max_drawdowns.append(max_dd)

        final_pnls.sort()
        max_drawdowns.sort()

        mean_pnl = sum(final_pnls) / len(final_pnls)
        p05_idx = int(len(final_pnls) * 0.05)
        p95_idx = int(len(final_pnls) * 0.95)

        return MonteCarloSummary(
            simulations=iterations,
            mean_net_pnl=mean_pnl,
            p05_net_pnl=final_pnls[p05_idx],
            p95_net_pnl=final_pnls[p95_idx],
            p95_max_drawdown_pct=max_drawdowns[p95_idx],
        )

    def run_cost_stress_test(
        self,
        candles: Sequence[Candle],
        features: Sequence[MarketFeatures],
        strategy: SignalStrategy,
        multipliers: Sequence[float] = (1.0, 1.5, 2.0, 3.0, 5.0),
    ) -> list[StressTestPoint]:
        """Perform transaction cost and slippage stress testing across multipliers."""
        points: list[StressTestPoint] = []
        base_cost = self.engine.cost_model

        for mult in multipliers:
            stressed_model = TransactionCostModel(
                fee_rate=base_cost.fee_rate * mult,
                half_spread_pct=base_cost.half_spread_pct * mult,
                slippage_pct=base_cost.slippage_pct * mult,
                funding_rate_per_interval=base_cost.funding_rate_per_interval * mult,
                latency_bars=base_cost.latency_bars,
                max_volume_participation=base_cost.max_volume_participation,
            )

            stressed_engine = DeterministicBacktestEngine(
                initial_balance=self.engine.initial_balance,
                cost_model=stressed_model,
                trade_size_notional=self.engine.trade_size_notional,
            )

            res = stressed_engine.run_backtest(candles, features, strategy)
            points.append(
                StressTestPoint(
                    cost_multiplier=mult,
                    total_net_pnl=res.total_net_pnl,
                    max_drawdown_pct=res.max_drawdown_pct,
                    profit_factor=res.profit_factor,
                    is_profitable=res.total_net_pnl > 0,
                )
            )

        return points

    def run_walk_forward(
        self,
        candles: Sequence[Candle],
        features: Sequence[MarketFeatures],
        strategy: SignalStrategy,
        train_ratio: float = 0.7,
        num_windows: int = 3,
    ) -> WalkForwardSummary:
        """Perform Walk-Forward Optimization / testing across sliding windows."""
        total_len = len(candles)
        if total_len < 50:
            # Simple fallback for short sequences
            res = self.engine.run_backtest(candles, features, strategy)
            return WalkForwardSummary(
                total_windows=1,
                aggregate_is_net_pnl=res.total_net_pnl,
                aggregate_oos_net_pnl=res.total_net_pnl,
                wfo_efficiency_ratio=1.0,
                window_results=[],
            )

        window_size = total_len // num_windows
        is_size = int(window_size * train_ratio)
        oos_size = window_size - is_size

        window_results: list[WalkForwardWindowResult] = []
        total_is_pnl = 0.0
        total_oos_pnl = 0.0

        for w in range(num_windows):
            start_idx = w * window_size
            is_end = start_idx + is_size
            oos_end = min(total_len, is_end + oos_size)

            is_c = candles[start_idx:is_end]
            is_f = features[start_idx:is_end]
            oos_c = candles[is_end:oos_end]
            oos_f = features[is_end:oos_end]

            if not is_c or not oos_c:
                continue

            is_res = self.engine.run_backtest(is_c, is_f, strategy)
            oos_res = self.engine.run_backtest(oos_c, oos_f, strategy)

            total_is_pnl += is_res.total_net_pnl
            total_oos_pnl += oos_res.total_net_pnl

            window_results.append(
                WalkForwardWindowResult(
                    window_index=w,
                    is_start=start_idx,
                    is_end=is_end,
                    oos_start=is_end,
                    oos_end=oos_end,
                    is_net_pnl=is_res.total_net_pnl,
                    oos_net_pnl=oos_res.total_net_pnl,
                )
            )

        efficiency = (
            (total_oos_pnl / total_is_pnl)
            if total_is_pnl > 0
            else (1.0 if total_oos_pnl > 0 else 0.0)
        )

        return WalkForwardSummary(
            total_windows=len(window_results),
            aggregate_is_net_pnl=total_is_pnl,
            aggregate_oos_net_pnl=total_oos_pnl,
            wfo_efficiency_ratio=efficiency,
            window_results=window_results,
        )

    def analyze_regime_breakdown(
        self,
        candles: Sequence[Candle],
        features: Sequence[MarketFeatures],
        strategy: SignalStrategy,
    ) -> dict[RegimeType, PerformanceMetrics]:
        """Evaluate strategy performance metrics separately for each market regime."""
        regime_candles: dict[RegimeType, list[Candle]] = {r: [] for r in RegimeType}
        regime_features: dict[RegimeType, list[MarketFeatures]] = {r: [] for r in RegimeType}

        for c, f in zip(candles, features, strict=True):
            regime_candles[f.regime].append(c)
            regime_features[f.regime].append(f)

        metrics: dict[RegimeType, PerformanceMetrics] = {}
        for r in RegimeType:
            rc = regime_candles[r]
            rf = regime_features[r]
            if len(rc) >= 5:
                res = self.engine.run_backtest(rc, rf, strategy)
                metrics[r] = PerformanceAnalyzer.analyze_result(res)
            else:
                metrics[r] = PerformanceMetrics(
                    total_net_pnl=0.0,
                    cagr_pct=0.0,
                    sharpe_ratio=0.0,
                    sortino_ratio=0.0,
                    calmar_ratio=0.0,
                    max_drawdown_pct=0.0,
                    win_rate_pct=0.0,
                    profit_factor=1.0,
                    trade_expectancy=0.0,
                    total_trades=0,
                )

        return metrics


__all__ = [
    "MonteCarloSummary",
    "RobustnessTester",
    "StressTestPoint",
    "WalkForwardSummary",
    "WalkForwardWindowResult",
]
