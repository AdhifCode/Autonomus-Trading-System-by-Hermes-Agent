"""Portfolio Accounting Module.

Handles position PnL calculations (Gross, Net, Realized, Unrealized),
fee deductions, funding cost tracking, and slippage cost accounting.

Rule: Net PnL = Gross PnL - fees - slippage - funding.
See implementation_spec.md §8.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.domain.enums import PositionSide


class TradeCostDetails(BaseModel):
    """Breakdown of transaction costs for a trade or position exit."""

    trading_fee: float = Field(default=0.0, ge=0.0)
    slippage_cost: float = Field(default=0.0, ge=0.0)
    funding_fee: float = Field(default=0.0)  # Can be positive (cost) or negative (income)


class PositionPnL(BaseModel):
    """PnL accounting details for a position."""

    symbol: str
    side: PositionSide
    quantity: float = Field(gt=0.0)
    entry_price: float = Field(gt=0.0)
    exit_or_current_price: float = Field(gt=0.0)
    gross_pnl: float
    net_pnl: float
    trading_fees: float = Field(default=0.0, ge=0.0)
    slippage_cost: float = Field(default=0.0, ge=0.0)
    funding_cost: float = Field(default=0.0)


class PositionAccounting:
    """Calculates position and portfolio PnL, fees, and net performance metrics."""

    @staticmethod
    def calculate_unrealized_pnl(
        side: PositionSide,
        quantity: float,
        entry_price: float,
        current_price: float,
    ) -> float:
        """Calculate gross unrealized PnL for an open position."""
        if side == PositionSide.LONG:
            return (current_price - entry_price) * quantity
        else:
            return (entry_price - current_price) * quantity

    @staticmethod
    def calculate_realized_pnl(
        side: PositionSide,
        quantity: float,
        entry_price: float,
        exit_price: float,
    ) -> float:
        """Calculate gross realized PnL for a closed position."""
        if side == PositionSide.LONG:
            return (exit_price - entry_price) * quantity
        else:
            return (entry_price - exit_price) * quantity

    @staticmethod
    def calculate_slippage_cost(
        intended_price: float,
        executed_price: float,
        quantity: float,
    ) -> float:
        """Calculate slippage cost incurred during execution."""
        return abs(executed_price - intended_price) * quantity

    @classmethod
    def calculate_position_pnl(
        self,
        symbol: str,
        side: PositionSide,
        quantity: float,
        entry_price: float,
        current_price: float,
        trading_fees: float = 0.0,
        slippage_cost: float = 0.0,
        funding_cost: float = 0.0,
        is_closed: bool = False,
    ) -> PositionPnL:
        """Calculate full PnL breakdown for open or closed position.

        Formula: Net PnL = Gross PnL - trading_fees - slippage_cost - funding_cost
        """
        if is_closed:
            gross = self.calculate_realized_pnl(side, quantity, entry_price, current_price)
        else:
            gross = self.calculate_unrealized_pnl(side, quantity, entry_price, current_price)

        net = gross - trading_fees - slippage_cost - funding_cost

        return PositionPnL(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            exit_or_current_price=current_price,
            gross_pnl=gross,
            net_pnl=net,
            trading_fees=trading_fees,
            slippage_cost=slippage_cost,
            funding_cost=funding_cost,
        )


__all__ = ["PositionAccounting", "PositionPnL", "TradeCostDetails"]
