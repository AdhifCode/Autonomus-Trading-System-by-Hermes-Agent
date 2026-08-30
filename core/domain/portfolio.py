"""Portfolio state domain model.

See implementation_spec.md §2, §11.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.domain.order import Order
from core.domain.position import Position


class PortfolioState(BaseModel):
    """Snapshot of current portfolio state.

    Drawdown is stored as decimal: 0.05 = 5% drawdown.
    Daily PnL resets at UTC midnight per architecture §11.
    """

    balance: float
    equity: float
    available_margin: float
    positions: list[Position] = Field(default_factory=list)
    exposure: float = Field(ge=0, description="Total notional exposure")
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    daily_pnl: float = 0.0
    drawdown: float = Field(
        default=0.0,
        ge=0,
        le=1.0,
        description="Current drawdown as decimal (0.05 = 5%)",
    )
    open_orders: list[Order] = Field(default_factory=list)
    timestamp: datetime

    @property
    def position_count(self) -> int:
        """Return number of open positions."""
        return len(self.positions)

    @property
    def open_order_count(self) -> int:
        """Return number of open orders."""
        return len(self.open_orders)

    @property
    def total_pnl(self) -> float:
        """Return combined realized + unrealized PnL."""
        return self.realized_pnl + self.unrealized_pnl
