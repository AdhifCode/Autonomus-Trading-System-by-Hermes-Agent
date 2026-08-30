"""Portfolio Calculator Module.

Calculates aggregate portfolio metrics: total equity, available margin,
gross/net exposure, leverage, daily/weekly PnL, and peak drawdown percentage.

See implementation_spec.md §8.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from core.domain.portfolio import PortfolioState
from core.domain.position import Position
from core.portfolio.accounting import PositionAccounting


class PortfolioSummary(BaseModel):
    """Aggregate snapshot of portfolio financial state and risk exposure metrics."""

    total_balance: float = Field(ge=0.0)
    available_balance: float = Field(ge=0.0)
    total_unrealized_pnl: float
    total_equity: float = Field(ge=0.0)
    total_gross_exposure: float = Field(ge=0.0)
    net_exposure: float
    leverage: float = Field(ge=0.0)
    peak_equity: float = Field(ge=0.0)
    drawdown_pct: float = Field(ge=0.0, le=100.0)
    daily_pnl: float = 0.0
    active_position_count: int = Field(ge=0)
    timestamp: datetime


class PortfolioCalculator:
    """Computes comprehensive portfolio state, exposure, and drawdown metrics."""

    def __init__(self, initial_peak_equity: float = 100_000.0) -> None:
        self.peak_equity = initial_peak_equity

    def update_peak_equity(self, current_equity: float) -> float:
        """Update high water mark peak equity if current equity exceeds prior peak."""
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        return self.peak_equity

    def calculate_drawdown_pct(self, current_equity: float) -> float:
        """Calculate peak-to-trough drawdown percentage.

        Formula: max(0.0, (peak_equity - current_equity) / peak_equity * 100.0)
        """
        peak = self.update_peak_equity(current_equity)
        if peak <= 0.0 or current_equity >= peak:
            return 0.0
        drawdown = ((peak - current_equity) / peak) * 100.0
        return min(100.0, max(0.0, drawdown))

    def calculate_portfolio_summary(
        self,
        wallet_balance: float,
        available_balance: float,
        positions: list[Position],
        daily_pnl: float = 0.0,
        timestamp: datetime | None = None,
    ) -> PortfolioSummary:
        """Calculate complete portfolio summary and metrics from positions and balance."""
        now = timestamp or datetime.now(tz=UTC)

        total_unrealized_pnl = 0.0
        gross_exposure = 0.0
        net_exposure = 0.0

        for pos in positions:
            unrealized = PositionAccounting.calculate_unrealized_pnl(
                side=pos.side,
                quantity=pos.quantity,
                entry_price=pos.entry_price,
                current_price=pos.current_price,
            )
            total_unrealized_pnl += unrealized

            notional = pos.quantity * pos.current_price
            gross_exposure += notional

            if pos.side.value.upper() == "LONG":
                net_exposure += notional
            else:
                net_exposure -= notional

        total_equity = wallet_balance + total_unrealized_pnl
        drawdown_pct = self.calculate_drawdown_pct(total_equity)
        leverage = gross_exposure / total_equity if total_equity > 0 else 0.0

        return PortfolioSummary(
            total_balance=wallet_balance,
            available_balance=available_balance,
            total_unrealized_pnl=total_unrealized_pnl,
            total_equity=max(0.0, total_equity),
            total_gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            leverage=leverage,
            peak_equity=self.peak_equity,
            drawdown_pct=drawdown_pct,
            daily_pnl=daily_pnl,
            active_position_count=len(positions),
            timestamp=now,
        )

    def to_portfolio_state(
        self, summary: PortfolioSummary, positions: list[Position] | None = None
    ) -> PortfolioState:
        """Convert PortfolioSummary snapshot into core domain PortfolioState model."""
        return PortfolioState(
            balance=summary.total_balance,
            equity=summary.total_equity,
            available_margin=summary.available_balance,
            positions=positions or [],
            exposure=summary.total_gross_exposure,
            realized_pnl=0.0,
            unrealized_pnl=summary.total_unrealized_pnl,
            daily_pnl=summary.daily_pnl,
            drawdown=summary.drawdown_pct / 100.0,
            open_orders=[],
            timestamp=summary.timestamp,
        )


__all__ = ["PortfolioCalculator", "PortfolioSummary"]
