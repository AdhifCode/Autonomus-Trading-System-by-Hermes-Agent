"""Order domain models.

See implementation_spec.md §2, §8.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from core.domain.enums import OrderSide, OrderStatus, OrderType


class OrderRequest(BaseModel):
    """Request to submit an order to the exchange.

    client_order_id follows the idempotency contract: TRD-YYYYMMDD-NNNNNN.
    """

    client_order_id: str = Field(
        pattern=r"^TRD-\d{8}-\d{6}$",
        description="Format: TRD-YYYYMMDD-NNNNNN",
    )
    proposal_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_price_requirements(self) -> OrderRequest:
        """Validate price fields based on order type."""
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("LIMIT orders require a price")
        if self.order_type == OrderType.STOP_LIMIT:
            if self.price is None:
                raise ValueError("STOP_LIMIT orders require a price")
            if self.stop_price is None:
                raise ValueError("STOP_LIMIT orders require a stop_price")
        if self.order_type == OrderType.STOP_MARKET and self.stop_price is None:
            raise ValueError("STOP_MARKET orders require a stop_price")
        return self


class Order(BaseModel):
    """An order in the system, tracking its full lifecycle."""

    client_order_id: str = Field(min_length=1)
    exchange_order_id: str | None = None
    proposal_id: str = Field(min_length=1)
    trade_id: str | None = None
    symbol: str = Field(min_length=1)
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(gt=0)
    filled_quantity: float = Field(default=0.0, ge=0)
    price: float | None = None
    stop_price: float | None = None
    average_fill_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_fill_quantities(self) -> Order:
        """Filled quantity must not exceed order quantity."""
        if self.filled_quantity > self.quantity:
            msg = f"filled_quantity ({self.filled_quantity}) exceeds quantity ({self.quantity})"
            raise ValueError(msg)
        return self

    @property
    def is_terminal(self) -> bool:
        """Return True if the order is in a terminal state."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    @property
    def remaining_quantity(self) -> float:
        """Return unfilled quantity."""
        return self.quantity - self.filled_quantity
