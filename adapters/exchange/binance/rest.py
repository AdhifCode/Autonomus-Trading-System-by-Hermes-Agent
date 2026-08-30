"""Binance REST API Client implementation.

Provides direct HTTP communication with Binance Testnet REST endpoints.
Enforces HMAC SHA256 authentication, rate limit tracking, strict timeouts,
error mapping, and live environment connection protection.

See implementation_spec.md §7.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from adapters.exchange.binance.error_mapper import map_binance_error
from core.errors import (
    ExchangeDisconnectedError,
    ExchangeError,
    ExchangeTimeoutError,
)
from core.logging import get_logger

logger = get_logger(__name__)

# Default Binance Futures Testnet Base URL
BINANCE_FUTURES_TESTNET_URL = "https://testnet.binancefuture.com"
BINANCE_SPOT_TESTNET_URL = "https://testnet.binance.vision"

# Forbidden Production Domains to prevent accidental live execution
PRODUCTION_DOMAINS = (
    "api.binance.com",
    "fapi.binance.com",
    "dapi.binance.com",
    "api1.binance.com",
    "api2.binance.com",
    "api3.binance.com",
)


class BinanceRESTClient:
    """HTTP REST Client for Binance Testnet endpoints."""

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = True,
        base_url: str | None = None,
        timeout_sec: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.timeout_sec = timeout_sec

        # Determine base URL
        self.base_url = (base_url or BINANCE_FUTURES_TESTNET_URL).rstrip("/")

        # Enforce Live Trading Protection Guard
        self._verify_live_protection()

        self._transport = transport
        self.last_used_weight: int = 0

    def _verify_live_protection(self) -> None:
        """Safety Invariant: Prevent connection to live production Binance endpoints."""
        if not self.testnet:
            raise ExchangeError("LIVE trading is strictly prohibited! testnet flag must be True.")

        for prod_domain in PRODUCTION_DOMAINS:
            if prod_domain in self.base_url:
                raise ExchangeError(
                    f"LIVE trading is strictly prohibited! "
                    f"Production domain '{prod_domain}' detected in base_url '{self.base_url}'."
                )

    def _generate_signature(self, params: dict[str, Any]) -> str:
        """Generate HMAC SHA256 signature for authenticated requests."""
        query_string = urlencode(params)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        """Execute HTTP request with signature, timeout, rate limit tracking, error mapping."""
        self._verify_live_protection()

        url = f"{self.base_url}{endpoint}"
        req_params = dict(params or {})

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "TradingSystem-BinanceAdapter/1.0",
        }
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        if signed:
            req_params["timestamp"] = int(time.time() * 1000)
            req_params["signature"] = self._generate_signature(req_params)

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_sec, transport=self._transport
            ) as client:
                if method.upper() == "GET":
                    response = await client.get(url, params=req_params, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(url, data=req_params, headers=headers)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, params=req_params, headers=headers)
                else:
                    response = await client.request(
                        method.upper(), url, params=req_params, headers=headers
                    )

            # Track rate limit weight header if present
            weight_hdr = response.headers.get("X-MBX-USED-WEIGHT-1M") or response.headers.get(
                "x-mbx-used-weight-1m"
            )
            if weight_hdr and weight_hdr.isdigit():
                self.last_used_weight = int(weight_hdr)

            # Handle non-2xx status codes
            if response.status_code >= 400:
                try:
                    err_json = response.json()
                except Exception:
                    err_json = {}
                raise map_binance_error(
                    status_code=response.status_code,
                    error_data=err_json,
                    message=response.text,
                )

            return response.json()

        except (httpx.TimeoutException, httpx.ConnectTimeout) as e:
            logger.warning("Binance REST request timed out for %s: %s", endpoint, e)
            raise ExchangeTimeoutError(f"Binance REST request timeout: {e}") from e
        except (httpx.NetworkError, httpx.ConnectError) as e:
            logger.warning("Binance REST network disconnection for %s: %s", endpoint, e)
            raise ExchangeDisconnectedError(f"Binance REST network disconnected: {e}") from e
        except Exception as e:
            if isinstance(e, (ExchangeError, ExchangeTimeoutError, ExchangeDisconnectedError)):
                raise
            raise map_binance_error(message=str(e)) from e

    async def get_account(self) -> dict[str, Any]:
        """Fetch Futures account summary."""
        res = await self._request("GET", "/fapi/v2/account", signed=True)
        if isinstance(res, dict):
            return res
        return {}

    async def get_positions(self) -> list[dict[str, Any]]:
        """Fetch Futures position risk summary."""
        data = await self._request("GET", "/fapi/v2/positionRisk", signed=True)
        if isinstance(data, list):
            return data
        return []

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Fetch open orders."""
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        data = await self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)
        if isinstance(data, list):
            return data
        return []

    async def get_order(
        self, symbol: str, client_order_id: str | None = None, order_id: int | None = None
    ) -> dict[str, Any]:
        """Fetch single order by client_order_id or order_id."""
        params: dict[str, Any] = {"symbol": symbol.upper()}
        if client_order_id:
            params["origClientOrderId"] = client_order_id
        elif order_id is not None:
            params["orderId"] = order_id
        else:
            raise ExchangeError("Must provide either client_order_id or order_id to get_order")

        res = await self._request("GET", "/fapi/v1/order", params=params, signed=True)
        if isinstance(res, dict):
            return res
        return {}

    async def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        client_order_id: str | None = None,
        time_in_force: str = "GTC",
    ) -> dict[str, Any]:
        """Submit new order to Binance Futures Testnet."""
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id

        if order_type.upper() in ("LIMIT", "STOP", "TAKE_PROFIT"):
            if price is None:
                raise ExchangeError(f"Price is required for {order_type} orders")
            params["price"] = price
            params["timeInForce"] = time_in_force

        res = await self._request("POST", "/fapi/v1/order", params=params, signed=True)
        if isinstance(res, dict):
            return res
        return {}

    async def cancel_order(
        self, symbol: str, client_order_id: str | None = None, order_id: int | None = None
    ) -> dict[str, Any]:
        """Cancel open order."""
        params: dict[str, Any] = {"symbol": symbol.upper()}
        if client_order_id:
            params["origClientOrderId"] = client_order_id
        elif order_id is not None:
            params["orderId"] = order_id
        else:
            raise ExchangeError("Must provide either client_order_id or order_id to cancel_order")

        res = await self._request("DELETE", "/fapi/v1/order", params=params, signed=True)
        if isinstance(res, dict):
            return res
        return {}

    async def get_market_data(self, symbol: str) -> dict[str, Any]:
        """Fetch order book ticker snapshot."""
        params = {"symbol": symbol.upper()}
        res = await self._request("GET", "/fapi/v1/ticker/bookTicker", params=params, signed=False)
        if isinstance(res, dict):
            return res
        return {}

    async def get_ohlcv(
        self, symbol: str, interval: str = "1m", limit: int = 100
    ) -> list[list[Any]]:
        """Fetch candlestick kline data."""
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
        }
        res = await self._request("GET", "/fapi/v1/klines", params=params, signed=False)
        if isinstance(res, list):
            return res
        return []


__all__ = ["BINANCE_FUTURES_TESTNET_URL", "BINANCE_SPOT_TESTNET_URL", "BinanceRESTClient"]
