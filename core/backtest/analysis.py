"""Performance Analytics Module.

Calculates comprehensive quantitative performance metrics for backtesting:
- CAGR (Compound Annual Growth Rate)
- Sharpe Ratio (annualized risk-adjusted return)
- Sortino Ratio (downside risk-adjusted return)
- Calmar Ratio (CAGR to Max Drawdown ratio)
- Profit Factor & Win Rate %
- Net PnL Expectancy

See implementation_spec.md §8.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, Field

from core.backtest.engine import BacktestResult


class PerformanceMetrics(BaseModel):
    """Quantitative performance and risk metrics summary."""

    total_net_pnl: float
    cagr_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float = Field(ge=0.0, le=100.0)
    win_rate_pct: float = Field(ge=0.0, le=100.0)
    profit_factor: float
    trade_expectancy: float
    total_trades: int


class PerformanceAnalyzer:
    """Computes risk and return metrics over equity curves and trade histories."""

    @staticmethod
    def calculate_sharpe_ratio(
        equity_curve: Sequence[float], risk_free_rate: float = 0.02, periods_per_year: int = 252
    ) -> float:
        """Calculate annualized Sharpe Ratio."""
        if len(equity_curve) < 2:
            return 0.0

        returns: list[float] = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            if prev > 0:
                returns.append((equity_curve[i] - prev) / prev)

        if not returns:
            return 0.0

        mean_ret = sum(returns) / len(returns)
        var = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std_ret = math.sqrt(var)

        if std_ret == 0:
            return 0.0

        daily_rf = risk_free_rate / periods_per_year
        return ((mean_ret - daily_rf) / std_ret) * math.sqrt(periods_per_year)

    @staticmethod
    def calculate_sortino_ratio(
        equity_curve: Sequence[float], risk_free_rate: float = 0.02, periods_per_year: int = 252
    ) -> float:
        """Calculate annualized Sortino Ratio (focusing on downside deviation)."""
        if len(equity_curve) < 2:
            return 0.0

        returns: list[float] = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            if prev > 0:
                returns.append((equity_curve[i] - prev) / prev)

        if not returns:
            return 0.0

        mean_ret = sum(returns) / len(returns)
        downside_returns = [min(0.0, r) for r in returns]
        downside_var = sum(r**2 for r in downside_returns) / len(returns)
        downside_std = math.sqrt(downside_var)

        if downside_std == 0:
            return 0.0

        daily_rf = risk_free_rate / periods_per_year
        return ((mean_ret - daily_rf) / downside_std) * math.sqrt(periods_per_year)

    @classmethod
    def analyze_result(
        cls, result: BacktestResult, periods_per_year: int = 252
    ) -> PerformanceMetrics:
        """Calculate complete PerformanceMetrics from a BacktestResult."""
        equity = result.equity_curve
        initial = result.initial_balance
        final = result.final_balance

        # Estimate CAGR assuming 1 bar = 1 period
        num_periods = max(1, len(equity) - 1)
        years = max(0.001, num_periods / periods_per_year)
        cagr = (
            (((final / initial) ** (1.0 / years)) - 1.0) * 100.0
            if initial > 0 and final > 0
            else 0.0
        )

        sharpe = cls.calculate_sharpe_ratio(equity, periods_per_year=periods_per_year)
        sortino = cls.calculate_sortino_ratio(equity, periods_per_year=periods_per_year)

        calmar = (
            (cagr / result.max_drawdown_pct)
            if result.max_drawdown_pct > 0
            else (cagr if cagr > 0 else 0.0)
        )
        expectancy = (
            (result.total_net_pnl / result.total_trades) if result.total_trades > 0 else 0.0
        )

        return PerformanceMetrics(
            total_net_pnl=result.total_net_pnl,
            cagr_pct=cagr,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown_pct=result.max_drawdown_pct,
            win_rate_pct=result.win_rate_pct,
            profit_factor=result.profit_factor,
            trade_expectancy=expectancy,
            total_trades=result.total_trades,
        )


__all__ = ["PerformanceAnalyzer", "PerformanceMetrics"]
