"""Abstract Exchange Adapter Interface.

Defines the contract for exchange connectivity (Mock, Binance, etc.).
See implementation_spec.md §7.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.domain.market_state import MarketState
from core.domain.order import Order
from core.domain.position import Position


class ExchangeAdapter(ABC):
    """Abstract interface for exchange connectivity."""

    @abstractmethod
    async def get_account(self) -> dict[str, float]:
        """Fetch account balances and equity."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Fetch active exchange positions."""
        ...

    @abstractmethod
    async def get_open_orders(self) -> list[Order]:
        """Fetch open exchange orders."""
        ...

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        """Query order state by client_order_id or exchange_order_id.

        Raises:
            RecordNotFoundError / OrderNotFoundError if order does not exist on exchange.
        """
        ...

    @abstractmethod
    async def submit_order(self, order: Order) -> Order:
        """Submit a new order to the exchange.

        Raises:
            ExchangeTimeoutError: On network timeout.
            ExchangeDisconnectedError: On network disconnection.
            ExchangeError: On exchange rejection.
        """
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order on the exchange."""
        ...

    @abstractmethod
    async def get_market_data(self, symbol: str) -> MarketState:
        """Fetch current market state snapshot for symbol."""
        ...

    @abstractmethod
    async def get_ohlcv(
        self, symbol: str, interval: str = "1m", limit: int = 100
    ) -> list[dict[str, Any]]:
        """Fetch OHLCV candlestick data."""
        ...


__all__ = ["ExchangeAdapter"]
