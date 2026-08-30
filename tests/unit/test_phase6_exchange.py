"""Comprehensive Unit Tests for Phase 6: Exchange Adapter.

Verifies:
- Abstract ExchangeAdapter interface contract stability
- MockExchange adapter functionality and failure injection
- Binance REST Client request signing, rate limit headers, and timeout handling
- Live Trading Protection Guard (blocks production endpoints)
- Binance Error Code mapping to domain exceptions
- Binance WebSocket Client advisory events, listener callbacks, and exponential backoff reconnects
- BinanceAdapter domain model translation and authoritative REST verification
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from adapters.exchange.base import ExchangeAdapter
from adapters.exchange.binance.adapter import BinanceAdapter
from adapters.exchange.binance.error_mapper import map_binance_error
from adapters.exchange.binance.rest import (
    BinanceRESTClient,
)
from adapters.exchange.binance.websocket import BinanceWebSocketClient
from adapters.exchange.mock.adapter import MockExchange
from core.domain.enums import OrderSide, OrderStatus, OrderType, PositionSide
from core.domain.order import Order
from core.errors import (
    ExchangeDisconnectedError,
    ExchangeError,
    ExchangeTimeoutError,
    RecordNotFoundError,
)

_NOW = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 1. Interface & Mock Exchange Tests
# ---------------------------------------------------------------------------


class TestExchangeAdapterInterface:
    def test_abstract_interface_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            ExchangeAdapter()  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_mock_adapter_implements_all_interface_methods(self):
        mock = MockExchange(balance=50_000.0)

        acct = await mock.get_account()
        assert acct["total"] == 50_000.0

        positions = await mock.get_positions()
        assert isinstance(positions, list)

        open_orders = await mock.get_open_orders()
        assert isinstance(open_orders, list)

        mkt = await mock.get_market_data("BTCUSDT")
        assert mkt.symbol == "BTCUSDT"

        ohlcv = await mock.get_ohlcv("BTCUSDT", limit=5)
        assert len(ohlcv) == 5

        order = Order(
            client_order_id="TRD-TEST-001",
            proposal_id="PRP-001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            created_at=_NOW,
            updated_at=_NOW,
        )
        sub = await mock.submit_order(order)
        assert sub.status == OrderStatus.FILLED

        fetched = await mock.get_order("TRD-TEST-001")
        assert fetched.client_order_id == "TRD-TEST-001"

        cancelled = await mock.cancel_order("TRD-TEST-001")
        assert cancelled is True


# ---------------------------------------------------------------------------
# 2. Error Mapper Tests
# ---------------------------------------------------------------------------


class TestBinanceErrorMapper:
    def test_unknown_order_errors(self):
        err1 = map_binance_error(
            status_code=404, error_data={"code": -2011, "msg": "Unknown order"}
        )
        assert isinstance(err1, RecordNotFoundError)

        err2 = map_binance_error(error_data={"code": -2013, "msg": "Order does not exist"})
        assert isinstance(err2, RecordNotFoundError)

    def test_timestamp_timeout(self):
        err = map_binance_error(
            error_data={"code": -1021, "msg": "Timestamp for this request was 1000ms ahead"}
        )
        assert isinstance(err, ExchangeTimeoutError)

    def test_rate_limit_exceeded(self):
        err1 = map_binance_error(status_code=429, error_data={"msg": "Too many requests"})
        assert isinstance(err1, ExchangeError)
        assert "rate limit" in str(err1).lower()

        err2 = map_binance_error(status_code=418, error_data={"msg": "IP banned"})
        assert isinstance(err2, ExchangeError)

    def test_authentication_error(self):
        err = map_binance_error(status_code=401, error_data={"code": -1002, "msg": "Unauthorized"})
        assert isinstance(err, ExchangeError)
        assert "authentication failed" in str(err).lower()

    def test_order_rejection(self):
        err = map_binance_error(
            error_data={"code": -2010, "msg": "Account has insufficient balance"}
        )
        assert isinstance(err, ExchangeError)
        assert "rejected" in str(err).lower()


# ---------------------------------------------------------------------------
# 3. Live Trading Protection Safety Tests
# ---------------------------------------------------------------------------


class TestBinanceLiveTradingProtection:
    def test_rest_client_blocks_live_flag(self):
        with pytest.raises(ExchangeError, match="LIVE trading is strictly prohibited"):
            BinanceRESTClient(testnet=False)

    def test_rest_client_blocks_production_domains(self):
        with pytest.raises(ExchangeError, match="Production domain"):
            BinanceRESTClient(testnet=True, base_url="https://fapi.binance.com")

        with pytest.raises(ExchangeError, match="Production domain"):
            BinanceRESTClient(testnet=True, base_url="https://api.binance.com")

    def test_ws_client_blocks_live_flag(self):
        with pytest.raises(ExchangeError, match="LIVE trading is strictly prohibited"):
            BinanceWebSocketClient(testnet=False)

    def test_adapter_blocks_live_flag(self):
        with pytest.raises(ExchangeError, match="LIVE trading is strictly prohibited"):
            BinanceAdapter(testnet=False)


# ---------------------------------------------------------------------------
# 4. Binance REST Client Unit Tests (Mocked Transport)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBinanceRESTClient:
    async def test_signature_generation(self):
        client = BinanceRESTClient(
            api_key="test_key",
            api_secret="test_secret_1234567890",
            testnet=True,
        )
        params = {"symbol": "BTCUSDT", "side": "BUY", "timestamp": 1600000000000}
        sig = client._generate_signature(params)
        assert len(sig) == 64  # SHA256 hex digest length

    async def test_get_account_endpoint(self):
        def handle_request(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/fapi/v2/account"
            assert "X-MBX-APIKEY" in request.headers
            return httpx.Response(
                200,
                json={
                    "totalWalletBalance": "100000.0",
                    "availableBalance": "95000.0",
                    "totalUnrealizedProfit": "500.0",
                },
                headers={"X-MBX-USED-WEIGHT-1M": "5"},
            )

        transport = httpx.MockTransport(handle_request)
        client = BinanceRESTClient(
            api_key="key",
            api_secret="secret",
            testnet=True,
            transport=transport,
        )

        res = await client.get_account()
        assert res["totalWalletBalance"] == "100000.0"
        assert client.last_used_weight == 5

    async def test_submit_order_endpoint(self):
        def handle_request(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/fapi/v1/order"
            body = request.read().decode("utf-8")
            assert "symbol=BTCUSDT" in body
            assert "side=BUY" in body
            assert "quantity=1.0" in body
            return httpx.Response(
                200,
                json={
                    "orderId": 12345,
                    "clientOrderId": "TRD-001",
                    "symbol": "BTCUSDT",
                    "status": "NEW",
                    "price": "50000.0",
                    "origQty": "1.0",
                    "executedQty": "0.0",
                },
            )

        transport = httpx.MockTransport(handle_request)
        client = BinanceRESTClient(
            api_key="key", api_secret="secret", testnet=True, transport=transport
        )

        res = await client.submit_order(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity=1.0,
            price=50000.0,
            client_order_id="TRD-001",
        )
        assert res["orderId"] == 12345
        assert res["status"] == "NEW"

    async def test_timeout_handling(self):
        def handle_request(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("Mocked timeout")

        transport = httpx.MockTransport(handle_request)
        client = BinanceRESTClient(
            api_key="key", api_secret="secret", testnet=True, transport=transport
        )

        with pytest.raises(ExchangeTimeoutError, match="request timeout"):
            await client.get_account()

    async def test_network_disconnect_handling(self):
        def handle_request(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handle_request)
        client = BinanceRESTClient(
            api_key="key", api_secret="secret", testnet=True, transport=transport
        )

        with pytest.raises(ExchangeDisconnectedError, match="disconnected"):
            await client.get_account()


# ---------------------------------------------------------------------------
# 5. Binance WebSocket Client Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBinanceWebSocketClient:
    async def test_connection_state_and_events(self):
        ws = BinanceWebSocketClient(testnet=True)
        assert ws.is_connected is False

        await ws.connect()
        assert ws.is_connected is True

        received_events: list[dict[str, Any]] = []

        async def advisory_callback(payload: dict[str, Any]) -> None:
            received_events.append(payload)

        ws.register_listener("ticker", advisory_callback)

        test_msg = {
            "e": "24hrTicker",
            "s": "BTCUSDT",
            "c": "50000.0",
        }
        await ws.process_incoming_message(test_msg)

        assert len(received_events) == 1
        assert received_events[0]["s"] == "BTCUSDT"

        await ws.disconnect()
        assert ws.is_connected is False

    async def test_exponential_backoff_reconnect(self):
        ws = BinanceWebSocketClient(
            testnet=True, max_reconnect_attempts=2, initial_backoff_sec=0.01
        )
        await ws.connect()

        # Simulate disconnect
        ws._connected = False

        # Should attempt reconnection and succeed
        await ws.handle_disconnect()
        assert ws.is_connected is True


# ---------------------------------------------------------------------------
# 6. Binance Adapter Orchestration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBinanceAdapterOrchestration:
    async def test_adapter_domain_mappings(self):
        def handle_request(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/fapi/v2/account":
                return httpx.Response(
                    200,
                    json={
                        "totalWalletBalance": "100000.0",
                        "availableBalance": "80000.0",
                        "totalUnrealizedProfit": "2000.0",
                    },
                )
            if path == "/fapi/v2/positionRisk":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "symbol": "BTCUSDT",
                            "positionAmt": "0.5",
                            "entryPrice": "48000.0",
                            "markPrice": "50000.0",
                            "unRealizedProfit": "1000.0",
                        }
                    ],
                )
            if path == "/fapi/v1/ticker/bookTicker":
                return httpx.Response(
                    200,
                    json={
                        "symbol": "BTCUSDT",
                        "bidPrice": "49995.0",
                        "askPrice": "50005.0",
                    },
                )
            return httpx.Response(404, json={"code": -404, "msg": "Not found"})

        transport = httpx.MockTransport(handle_request)
        rest_client = BinanceRESTClient(
            api_key="key", api_secret="secret", testnet=True, transport=transport
        )
        adapter = BinanceAdapter(testnet=True, rest_client=rest_client)

        # 1. Test get_account
        acct = await adapter.get_account()
        assert acct["total"] == 100000.0
        assert acct["available"] == 80000.0
        assert acct["equity"] == 102000.0

        # 2. Test get_positions
        positions = await adapter.get_positions()
        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "BTCUSDT"
        assert pos.side == PositionSide.LONG
        assert pos.quantity == 0.5
        assert pos.entry_price == 48000.0

        # 3. Test get_market_data
        mkt = await adapter.get_market_data("BTCUSDT")
        assert mkt.symbol == "BTCUSDT"
        assert mkt.price == 50000.0
        assert mkt.spread == 10.0
