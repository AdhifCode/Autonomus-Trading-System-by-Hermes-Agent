"""Fill domain model.

Represents a single execution fill from the exchange.
See implementation_spec.md §2.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.domain.enums import OrderSide


class Fill(BaseModel):
    """A single fill event from the exchange."""

    fill_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: OrderSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(ge=0)
    fee_currency: str = Field(min_length=1)
    timestamp: datetime

    @property
    def notional(self) -> float:
        """Return the notional value of this fill (price x quantity)."""
        return self.price * self.quantity

    @property
    def net_cost(self) -> float:
        """Return fill notional plus fee."""
        return self.notional + self.fee
