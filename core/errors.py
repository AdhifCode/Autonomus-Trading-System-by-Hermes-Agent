"""Exception hierarchy for the trading system.

All exceptions inherit from TradingSystemError.
Error codes follow the convention in implementation_spec.md §18.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Canonical error codes. One per failure category.

    Prefixes:
        RISK_  — Risk Engine violations
        EXEC_  — Execution Service failures
        SYS_   — System-level errors
        HERMES_ — Hermes integration boundary errors
    """

    # Risk — one per validator from architecture §7
    RISK_POSITION_SIZE = "RISK_001"
    RISK_PORTFOLIO_EXPOSURE = "RISK_002"
    RISK_DAILY_LOSS = "RISK_003"
    RISK_WEEKLY_LOSS = "RISK_004"
    RISK_DRAWDOWN = "RISK_005"
    RISK_KILL_SWITCH = "RISK_006"
    RISK_TRADING_MODE = "RISK_007"
    RISK_STALE_DATA = "RISK_008"
    RISK_SPREAD = "RISK_009"
    RISK_LIQUIDITY = "RISK_010"
    RISK_SYMBOL_EXPOSURE = "RISK_011"
    RISK_STRATEGY_EXPOSURE = "RISK_012"
    RISK_CORRELATED_EXPOSURE = "RISK_013"
    RISK_ORDER_NOTIONAL = "RISK_014"
    RISK_CONCURRENT_POSITIONS = "RISK_015"
    RISK_CONCURRENT_ORDERS = "RISK_016"
    RISK_LEVERAGE = "RISK_017"
    RISK_SLIPPAGE = "RISK_018"
    RISK_PRICE_DEVIATION = "RISK_019"
    RISK_MACRO_EVENT = "RISK_020"

    # Execution
    EXEC_DUPLICATE_ORDER = "EXEC_001"
    EXEC_INVALID_TRANSITION = "EXEC_002"
    EXEC_EXCHANGE_TIMEOUT = "EXEC_003"
    EXEC_EXCHANGE_REJECTED = "EXEC_004"
    EXEC_RECONCILIATION_MISMATCH = "EXEC_005"

    # System
    SYS_EXCHANGE_DISCONNECTED = "SYS_001"
    SYS_DATABASE_ERROR = "SYS_002"
    SYS_CONFIG_ERROR = "SYS_003"
    SYS_DATA_VALIDATION = "SYS_004"
    SYS_TEMPORAL_LEAKAGE = "SYS_005"
    SYS_STRATEGY_LIFECYCLE = "SYS_006"
    SYS_STRATEGY_IMMUTABILITY = "SYS_007"

    # Hermes
    HERMES_UNAUTHORIZED = "HERMES_001"
    HERMES_INVALID_PROPOSAL = "HERMES_002"
    HERMES_BLOCKED_OPERATION = "HERMES_003"


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------


class TradingSystemError(Exception):
    """Root exception for the trading system."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.details = details or {}
        super().__init__(message)


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------


class ConfigError(TradingSystemError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code=ErrorCode.SYS_CONFIG_ERROR, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Database errors
# ---------------------------------------------------------------------------


class DatabaseError(TradingSystemError):
    """Raised when a database operation fails."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code=ErrorCode.SYS_DATABASE_ERROR, **kwargs)  # type: ignore[arg-type]


class MigrationError(DatabaseError):
    """Raised when a database migration fails."""


class RecordNotFoundError(DatabaseError):
    """Raised when a requested database record is not found."""


# ---------------------------------------------------------------------------
# Risk errors
# ---------------------------------------------------------------------------


class RiskError(TradingSystemError):
    """Raised when a risk check fails."""


class RiskPolicyError(RiskError):
    """Raised when risk policy configuration is invalid."""


# ---------------------------------------------------------------------------
# Execution errors
# ---------------------------------------------------------------------------


class ExecutionError(TradingSystemError):
    """Raised during order execution."""


class DuplicateOrderError(ExecutionError):
    """Raised when a duplicate order is detected."""

    def __init__(self, order_id: str) -> None:
        super().__init__(
            f"Duplicate order detected: {order_id}",
            code=ErrorCode.EXEC_DUPLICATE_ORDER,
            details={"order_id": order_id},
        )


class InvalidStateTransitionError(ExecutionError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(
            f"Invalid state transition: {from_state} → {to_state}",
            code=ErrorCode.EXEC_INVALID_TRANSITION,
            details={"from_state": from_state, "to_state": to_state},
        )


# ---------------------------------------------------------------------------
# Exchange errors
# ---------------------------------------------------------------------------


class ExchangeError(TradingSystemError):
    """Raised when an exchange operation fails."""


class ExchangeDisconnectedError(ExchangeError):
    """Raised when the exchange connection is lost."""

    def __init__(self, message: str = "Exchange disconnected") -> None:
        super().__init__(message, code=ErrorCode.SYS_EXCHANGE_DISCONNECTED)


class ExchangeTimeoutError(ExchangeError):
    """Raised when an exchange request times out."""

    def __init__(self, message: str = "Exchange request timed out") -> None:
        super().__init__(message, code=ErrorCode.EXEC_EXCHANGE_TIMEOUT)


# ---------------------------------------------------------------------------
# Hermes integration errors
# ---------------------------------------------------------------------------


class HermesError(TradingSystemError):
    """Raised for Hermes integration boundary violations."""


class HermesUnauthorizedError(HermesError):
    """Raised when Hermes attempts an unauthorized operation."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"Unauthorized Hermes operation: {operation}",
            code=ErrorCode.HERMES_UNAUTHORIZED,
            details={"operation": operation},
        )


class HermesBlockedOperationError(HermesError):
    """Raised when Hermes attempts a blocked operation."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"Blocked operation: {operation}",
            code=ErrorCode.HERMES_BLOCKED_OPERATION,
            details={"operation": operation},
        )


class HermesInvalidProposalError(HermesError):
    """Raised when a TradeProposal submitted by Hermes fails schema validation."""

    def __init__(self, message: str) -> None:
        super().__init__(
            f"Invalid Hermes proposal: {message}",
            code=ErrorCode.HERMES_INVALID_PROPOSAL,
        )


# ---------------------------------------------------------------------------
# Data & Backtest errors
# ---------------------------------------------------------------------------


class DataValidationError(TradingSystemError):
    """Raised when market data fails validation rules."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code=ErrorCode.SYS_DATA_VALIDATION)


class TemporalLeakageError(TradingSystemError):
    """Raised when look-ahead bias or temporal data leakage is detected."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code=ErrorCode.SYS_TEMPORAL_LEAKAGE)


class StrategyLifecycleError(TradingSystemError):
    """Raised when an invalid strategy lifecycle state transition is attempted."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code=ErrorCode.SYS_STRATEGY_LIFECYCLE)


class StrategyImmutabilityError(TradingSystemError):
    """Raised when an attempt is made to mutate a production or immutable strategy version."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code=ErrorCode.SYS_STRATEGY_IMMUTABILITY)
