"""Position domain model.

Implements PnL calculation per architecture §11:
    - Long PnL = (current_price - entry_price) x quantity
    - Short PnL = (entry_price - current_price) x quantity
    - Net PnL = Gross PnL - fees - slippage - funding

All percentages stored as decimals (0.0165, not "1.65%").
See implementation_spec.md §2, §11.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.domain.enums import PositionSide


class Position(BaseModel):
    """An open or historical trading position with PnL tracking."""

    position_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: PositionSide
    quantity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    current_price: float = Field(gt=0)
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_fees: float = Field(default=0.0, ge=0)
    total_funding: float = 0.0
    total_slippage: float = Field(default=0.0, ge=0)
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    opened_at: datetime
    closed_at: datetime | None = None
    updated_at: datetime

    @property
    def gross_pnl(self) -> float:
        """Calculate gross unrealized PnL based on side.

        Long:  (current_price - entry_price) x quantity
        Short: (entry_price - current_price) x quantity
        """
        if self.side == PositionSide.LONG:
            return (self.current_price - self.entry_price) * self.quantity
        return (self.entry_price - self.current_price) * self.quantity

    @property
    def net_pnl(self) -> float:
        """Calculate net PnL (gross - fees - slippage - funding)."""
        return self.gross_pnl - self.total_fees - self.total_slippage - self.total_funding

    @property
    def notional(self) -> float:
        """Current notional value of this position."""
        return self.current_price * self.quantity

    @property
    def entry_notional(self) -> float:
        """Notional value at entry."""
        return self.entry_price * self.quantity

    @property
    def return_pct(self) -> float:
        """Return as decimal (0.05 = 5%). Based on net PnL."""
        if self.entry_notional == 0:
            return 0.0
        return self.net_pnl / self.entry_notional
