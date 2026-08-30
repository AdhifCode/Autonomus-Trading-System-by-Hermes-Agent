"""Mock Exchange Adapter implementation.

Simulates exchange behaviors and failure scenarios for testing:
FILLED, PARTIAL_FILL, REJECTED, TIMEOUT, NETWORK_ERROR, UNKNOWN_ORDER, CANCELLED, DUPLICATE_REQUEST.

See implementation_spec.md §7.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from adapters.exchange.base import ExchangeAdapter
from core.domain.enums import OrderSide, OrderStatus, PositionSide
from core.domain.market_state import MarketState
from core.domain.order import Order
from core.domain.position import Position
from core.errors import (
    ExchangeDisconnectedError,
    ExchangeError,
    ExchangeTimeoutError,
    RecordNotFoundError,
)
from core.logging import get_logger

logger = get_logger(__name__)


class MockExchange(ExchangeAdapter):
    """Mock Exchange Adapter supporting configurable failure mode injections."""

    def __init__(
        self,
        balance: float = 100_000.0,
        simulated_latency_sec: float = 0.0,
        default_fill_mode: str = "FILLED",
    ) -> None:
        self._balance = balance
        self._latency = simulated_latency_sec
        self.fill_mode = default_fill_mode

        self._orders: dict[str, Order] = {}
        self._positions: dict[str, Position] = {}
        self._market_prices: dict[str, float] = {
            "BTCUSDT": 50000.0,
            "ETHUSDT": 3000.0,
            "SOLUSDT": 150.0,
        }
        self._processed_client_order_ids: set[str] = set()
        self._next_exchange_order_id = 1000

    def set_market_price(self, symbol: str, price: float) -> None:
        self._market_prices[symbol] = price

    def inject_failure(self, mode: str) -> None:
        """Inject a specific failure mode for subsequent requests.

        Supported modes:
            'FILLED', 'PARTIAL_FILL', 'REJECTED', 'TIMEOUT',
            'NETWORK_ERROR', 'UNKNOWN_ORDER', 'CANCELLED', 'DUPLICATE_REQUEST'
        """
        self.fill_mode = mode

    async def _simulate_latency(self) -> None:
        if self._latency > 0:
            await asyncio.sleep(self._latency)

    def _check_failure_injection(self) -> None:
        pass

    async def get_account(self) -> dict[str, float]:
        await self._simulate_latency()
        if self.fill_mode == "NETWORK_ERROR":
            raise ExchangeDisconnectedError("Simulated network disconnection")
        if self.fill_mode == "TIMEOUT":
            raise ExchangeTimeoutError("Simulated request timeout")
        return {
            "total": self._balance,
            "available": self._balance,
            "equity": self._balance,
        }

    async def get_positions(self) -> list[Position]:
        await self._simulate_latency()
        if self.fill_mode == "NETWORK_ERROR":
            raise ExchangeDisconnectedError("Simulated network disconnection")
        if self.fill_mode == "TIMEOUT":
            raise ExchangeTimeoutError("Simulated request timeout")
        return list(self._positions.values())

    async def get_open_orders(self) -> list[Order]:
        await self._simulate_latency()
        if self.fill_mode == "NETWORK_ERROR":
            raise ExchangeDisconnectedError("Simulated network disconnection")
        if self.fill_mode == "TIMEOUT":
            raise ExchangeTimeoutError("Simulated request timeout")
        return [
            o
            for o in self._orders.values()
            if o.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL)
        ]

    async def get_order(self, order_id: str) -> Order:
        await self._simulate_latency()

        # Check existing orders first (for query recovery)
        if order_id in self._orders:
            return self._orders[order_id]
        for order in self._orders.values():
            if order.client_order_id == order_id or order.exchange_order_id == order_id:
                return order

        if self.fill_mode == "NETWORK_ERROR":
            raise ExchangeDisconnectedError("Network disconnected during get_order")
        if self.fill_mode == "TIMEOUT":
            raise ExchangeTimeoutError("Timeout during get_order query")
        if self.fill_mode == "UNKNOWN_ORDER":
            raise RecordNotFoundError(f"Order {order_id} not found on exchange")

        raise RecordNotFoundError(f"Order {order_id} not found on exchange")

    async def submit_order(self, order: Order) -> Order:
        await self._simulate_latency()

        # Handle DUPLICATE_REQUEST or duplicate client_order_id
        if (
            self.fill_mode == "DUPLICATE_REQUEST"
            or order.client_order_id in self._processed_client_order_ids
        ):
            raise ExchangeError(f"Duplicate client order ID on exchange: {order.client_order_id}")

        if self.fill_mode == "REJECTED":
            raise ExchangeError(
                f"Exchange rejected order {order.client_order_id}: Insufficient margin"
            )

        if self.fill_mode == "TIMEOUT":
            # Note: order is saved internally on exchange to simulate timeout
            # where request reached exchange
            self._processed_client_order_ids.add(order.client_order_id)
            ex_id = f"EX-{self._next_exchange_order_id}"
            self._next_exchange_order_id += 1
            submitted = order.model_copy(
                update={"status": OrderStatus.SUBMITTED, "exchange_order_id": ex_id}
            )
            self._orders[order.client_order_id] = submitted
            raise ExchangeTimeoutError(
                f"Network request timed out during submission for {order.client_order_id}"
            )

        if self.fill_mode == "NETWORK_ERROR":
            raise ExchangeDisconnectedError("Network socket closed during order submission")

        # Record submission
        self._processed_client_order_ids.add(order.client_order_id)
        ex_id = f"EX-{self._next_exchange_order_id}"
        self._next_exchange_order_id += 1
        now = datetime.now(tz=UTC)

        current_price = self._market_prices.get(order.symbol, order.price or 50000.0)
        order_price = order.price if order.price is not None else current_price

        if self.fill_mode == "PARTIAL_FILL":
            partial_qty = round(order.quantity * 0.5, 6)
            updated_order = order.model_copy(
                update={
                    "exchange_order_id": ex_id,
                    "status": OrderStatus.PARTIAL,
                    "filled_quantity": partial_qty,
                    "average_fill_price": order_price,
                    "updated_at": now,
                }
            )
        elif self.fill_mode == "FILLED":
            updated_order = order.model_copy(
                update={
                    "exchange_order_id": ex_id,
                    "status": OrderStatus.FILLED,
                    "filled_quantity": order.quantity,
                    "average_fill_price": order_price,
                    "updated_at": now,
                }
            )
        elif self.fill_mode == "CANCELLED":
            updated_order = order.model_copy(
                update={
                    "exchange_order_id": ex_id,
                    "status": OrderStatus.CANCELLED,
                    "filled_quantity": 0.0,
                    "updated_at": now,
                }
            )
        else:
            updated_order = order.model_copy(
                update={
                    "exchange_order_id": ex_id,
                    "status": OrderStatus.SUBMITTED,
                    "updated_at": now,
                }
            )

        self._orders[order.client_order_id] = updated_order

        # Update mock position if filled
        if updated_order.status == OrderStatus.FILLED:
            pos_side = PositionSide.LONG if order.side == OrderSide.BUY else PositionSide.SHORT
            pos_id = f"POS-{order.symbol}"
            self._positions[pos_id] = Position(
                position_id=pos_id,
                symbol=order.symbol,
                side=pos_side,
                quantity=updated_order.filled_quantity,
                entry_price=updated_order.average_fill_price or order_price,
                current_price=order_price,
                strategy_id="mock_strategy",
                strategy_version="1.0",
                opened_at=now,
                updated_at=now,
            )

        return updated_order

    async def cancel_order(self, order_id: str) -> bool:
        await self._simulate_latency()
        if order_id in self._orders:
            o = self._orders[order_id]
            self._orders[order_id] = o.model_copy(
                update={
                    "status": OrderStatus.CANCELLED,
                    "updated_at": datetime.now(tz=UTC),
                }
            )
            return True
        return False

    async def get_market_data(self, symbol: str) -> MarketState:
        await self._simulate_latency()
        price = self._market_prices.get(symbol, 50000.0)
        return MarketState(
            symbol=symbol,
            price=price,
            bid=price - 5.0,
            ask=price + 5.0,
            spread=10.0,
            volume_24h=1_000_000.0,
            timestamp=datetime.now(tz=UTC),
            data_age_seconds=1.0,
        )

    async def get_ohlcv(
        self, symbol: str, interval: str = "1m", limit: int = 100
    ) -> list[dict[str, Any]]:
        await self._simulate_latency()
        price = self._market_prices.get(symbol, 50000.0)
        return [
            {
                "timestamp": datetime.now(tz=UTC).timestamp(),
                "open": price,
                "high": price + 10.0,
                "low": price - 10.0,
                "close": price,
                "volume": 100.0,
            }
            for _ in range(limit)
        ]


__all__ = ["MockExchange"]
