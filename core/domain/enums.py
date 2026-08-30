"""Domain enumerations for the trading system.

All enums use StrEnum for JSON-serializable values.
See implementation_spec.md §1.
"""

from __future__ import annotations

from enum import StrEnum


class TradingMode(StrEnum):
    """Trading environment modes (architecture §34)."""

    DEVELOPMENT = "DEVELOPMENT"
    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    TESTNET = "TESTNET"
    LIMITED_LIVE = "LIMITED_LIVE"
    LIVE = "LIVE"


class OrderSide(StrEnum):
    """Order direction."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Order execution type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(StrEnum):
    """Order lifecycle status."""

    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PositionSide(StrEnum):
    """Position direction."""

    LONG = "LONG"
    SHORT = "SHORT"


class MarketRegime(StrEnum):
    """Market regime classification (architecture §22)."""

    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"


class RiskDecisionType(StrEnum):
    """Risk Engine decision outcome."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FREEZE = "FREEZE"


class ExecutionState(StrEnum):
    """Execution lifecycle states (implementation_spec §5).

    RISK_REJECTED and EXCHANGE_REJECTED are distinct to avoid
    ambiguity in state tracking (see ambiguity #9).
    """

    PROPOSAL_CREATED = "PROPOSAL_CREATED"
    RISK_PENDING = "RISK_PENDING"
    RISK_REJECTED = "RISK_REJECTED"
    APPROVED = "APPROVED"
    EXECUTION_PENDING = "EXECUTION_PENDING"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    EXCHANGE_REJECTED = "EXCHANGE_REJECTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    POSITION_ACTIVE = "POSITION_ACTIVE"
    EXIT_PENDING = "EXIT_PENDING"
    POSITION_CLOSED = "POSITION_CLOSED"
    RECONCILED = "RECONCILED"
    UNKNOWN = "UNKNOWN"
    FREEZE = "FREEZE"
    RECONCILING = "RECONCILING"
    RESOLVED = "RESOLVED"


class StrategyLifecycle(StrEnum):
    """Strategy lifecycle stages (architecture §18)."""

    IDEA = "IDEA"
    RESEARCH = "RESEARCH"
    CANDIDATE = "CANDIDATE"
    BACKTEST = "BACKTEST"
    VALIDATED = "VALIDATED"
    PAPER = "PAPER"
    APPROVED = "APPROVED"
    PRODUCTION = "PRODUCTION"
    DEPRECATED = "DEPRECATED"


class KillSwitchState(StrEnum):
    """Kill switch states (architecture §30)."""

    ACTIVE = "ACTIVE"
    SOFT_KILL = "SOFT_KILL"
    HARD_KILL = "HARD_KILL"


class EventType(StrEnum):
    """Audit event types (implementation_spec §10)."""

    TRADE_PROPOSED = "TRADE_PROPOSED"
    RISK_EVALUATED = "RISK_EVALUATED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
    RECONCILIATION_STARTED = "RECONCILIATION_STARTED"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"
    STATE_TRANSITION = "STATE_TRANSITION"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    DATA_STALE = "DATA_STALE"
    EXCHANGE_DISCONNECTED = "EXCHANGE_DISCONNECTED"
    HERMES_TOOL_DISPATCHED = "HERMES_TOOL_DISPATCHED"
    HERMES_PROPOSAL_RECEIVED = "HERMES_PROPOSAL_RECEIVED"


class Severity(StrEnum):
    """Log/event severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
