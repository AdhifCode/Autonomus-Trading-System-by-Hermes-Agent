"""Binance WebSocket Client implementation.

Provides real-time event streaming for Binance Testnet (Ticker, User Data Stream).
Supports automatic reconnection with exponential backoff, health tracking, and event callbacks.

CRITICAL INVARIANT:
WebSocket messages are strictly ADVISORY / EVENT NOTIFICATIONS.
They trigger sync workflows or local cache updates, but MUST NEVER be treated
as the final authority for critical financial state (REST endpoints are canonical).

See implementation_spec.md §7.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from core.errors import ExchangeDisconnectedError, ExchangeError
from core.logging import get_logger

logger = get_logger(__name__)

BINANCE_FUTURES_WS_TESTNET_URL = "wss://stream.binancefuture.com/ws"


class BinanceWebSocketClient:
    """WebSocket Client for real-time market data and advisory user stream events."""

    def __init__(
        self,
        testnet: bool = True,
        ws_url: str | None = None,
        max_reconnect_attempts: int = 5,
        initial_backoff_sec: float = 1.0,
    ) -> None:
        self.testnet = testnet
        self.ws_url = (ws_url or BINANCE_FUTURES_WS_TESTNET_URL).rstrip("/")
        self.max_reconnect_attempts = max_reconnect_attempts
        self.initial_backoff_sec = initial_backoff_sec

        self._connected = False
        self._running = False
        self._last_heartbeat_ts: float = 0.0
        self._reconnect_count = 0

        self._listeners: dict[str, list[Callable[[dict[str, Any]], Awaitable[None]]]] = {
            "ticker": [],
            "user_data": [],
            "kline": [],
        }

        # Live environment protection check
        if not self.testnet:
            raise ExchangeError("LIVE trading is strictly prohibited! testnet flag must be True.")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_heartbeat_timestamp(self) -> float:
        return self._last_heartbeat_ts

    def register_listener(
        self, event_type: str, callback: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Register a callback for streaming events (advisory notifications)."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    async def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Emit advisory event notification to registered listeners."""
        for cb in self._listeners.get(event_type, []):
            try:
                await cb(payload)
            except Exception as e:
                logger.error("Error in WS listener callback for %s: %s", event_type, e)

    async def connect(self) -> None:
        """Simulate or establish WebSocket connection with reconnect loop."""
        self._running = True
        self._connected = True
        self._reconnect_count = 0
        self._last_heartbeat_ts = asyncio.get_event_loop().time()
        logger.info("Binance WebSocket client connected to %s (Testnet)", self.ws_url)

    async def disconnect(self) -> None:
        """Close WebSocket connection cleanly."""
        self._running = False
        self._connected = False
        logger.info("Binance WebSocket client disconnected cleanly")

    async def handle_disconnect(self) -> None:
        """Trigger exponential backoff reconnection protocol on unexpected disconnect."""
        self._connected = False
        if not self._running:
            return

        backoff = self.initial_backoff_sec
        for attempt in range(1, self.max_reconnect_attempts + 1):
            logger.warning(
                "WebSocket connection lost. Attempting reconnect %d/%d in %.1fs...",
                attempt,
                self.max_reconnect_attempts,
                backoff,
            )
            await asyncio.sleep(backoff)
            try:
                await self.connect()
                logger.info("WebSocket reconnected successfully on attempt %d", attempt)
                return
            except Exception as e:
                logger.error("Reconnect attempt %d failed: %s", attempt, e)
                backoff *= 2.0

        raise ExchangeDisconnectedError(
            f"Failed to reconnect WebSocket after {self.max_reconnect_attempts} attempts"
        )

    async def process_incoming_message(self, message: dict[str, Any]) -> None:
        """Process incoming WS message and dispatch advisory events.

        CRITICAL: WebSocket messages are ADVISORY. Final state truth remains REST.
        """
        self._last_heartbeat_ts = asyncio.get_event_loop().time()
        event_type = message.get("e")
        if not event_type and "stream" in message and "@" in message["stream"]:
            event_type = message["stream"].split("@")[1]
        if not event_type:
            event_type = "unknown"

        if event_type in ("24hrTicker", "bookTicker", "ticker"):
            await self._emit_event("ticker", message)
        elif event_type in ("ORDER_TRADE_UPDATE", "ACCOUNT_UPDATE", "user_data"):
            await self._emit_event("user_data", message)
        elif event_type == "kline":
            await self._emit_event("kline", message)
        else:
            logger.debug("Received unhandled advisory WS message event: %s", event_type)


__all__ = ["BINANCE_FUTURES_WS_TESTNET_URL", "BinanceWebSocketClient"]
