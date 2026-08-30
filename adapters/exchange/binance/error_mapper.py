"""Binance API Error Mapper.

Maps Binance HTTP status codes, network exceptions, and internal JSON error codes
to system domain exceptions (ExchangeError, ExchangeTimeoutError, etc.).
See implementation_spec.md §7.
"""

from __future__ import annotations

from typing import Any

from core.errors import (
    ExchangeError,
    ExchangeTimeoutError,
    RecordNotFoundError,
)


def map_binance_error(
    status_code: int | None = None,
    error_data: dict[str, Any] | None = None,
    message: str | None = None,
) -> Exception:
    """Map Binance API HTTP status code and JSON payload to domain exception.

    Binance JSON Error Codes:
    - -1021: INVALID_TIMESTAMP / Timestamp ahead of server / Timed out
    - -1013: INVALID_PRICE / INVALID_QUANTITY
    - -2010: NEW_ORDER_REJECTED (e.g. Insufficient Balance, Immediate cancel)
    - -2011: CANCEL_REJECTED (e.g. Unknown order)
    - -2013: NO_SUCH_ORDER (Unknown order)
    - -1003: TOO_MANY_REQUESTS / Rate limit exceeded
    - -1002: UNAUTHORIZED / Signature verification failed
    """
    error_code = error_data.get("code") if error_data else None
    error_msg = (
        error_data.get("msg")
        if error_data and "msg" in error_data
        else (message or "Unknown Binance error")
    )

    # 1. Unknown / Non-existent order checks
    if error_code in (-2011, -2013) or status_code == 404:
        return RecordNotFoundError(f"Order not found on Binance: {error_msg}")

    # 2. Timeout / Timestamp issues
    if error_code == -1021:
        return ExchangeTimeoutError(f"Binance timestamp timeout: {error_msg}")

    # 3. Rate limiting (429 / 418 / -1003)
    if status_code in (429, 418) or error_code == -1003:
        return ExchangeError(
            f"Binance rate limit exceeded ({status_code or error_code}): {error_msg}"
        )

    # 4. Authentication / Authorization (401 / 403 / -1002)
    if status_code in (401, 403) or error_code == -1002:
        return ExchangeError(f"Binance authentication failed: {error_msg}")

    # 5. Order rejections (-2010, -1013)
    if error_code in (-2010, -1013):
        return ExchangeError(f"Binance order rejected: {error_msg}")

    # 6. Default fallback
    return ExchangeError(f"Binance error (HTTP {status_code}, Code {error_code}): {error_msg}")


__all__ = ["map_binance_error"]
