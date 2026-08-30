"""Core domain package — all domain models and enumerations.

Provides re-exports for convenient access.
"""

from core.domain.enums import (
    EventType,
    ExecutionState,
    KillSwitchState,
    MarketRegime,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    RiskDecisionType,
    Severity,
    StrategyLifecycle,
    TradingMode,
)
from core.domain.events import AuditEvent
from core.domain.fill import Fill
from core.domain.market_state import OHLCV, AccountInfo, MarketState, OrderBook, OrderBookEntry
from core.domain.order import Order, OrderRequest
from core.domain.portfolio import PortfolioState
from core.domain.position import Position
from core.domain.risk import RiskDecision, RiskPolicy, RiskViolation
from core.domain.strategy import StrategyVersion
from core.domain.system_state import SystemState
from core.domain.trade_proposal import (
    EntrySpec,
    PositionSizeSpec,
    StopLossSpec,
    TakeProfitSpec,
    TradeProposal,
)

__all__ = [
    "OHLCV",
    "AccountInfo",
    "AuditEvent",
    "EntrySpec",
    "EventType",
    "ExecutionState",
    "Fill",
    "KillSwitchState",
    "MarketRegime",
    "MarketState",
    "Order",
    "OrderBook",
    "OrderBookEntry",
    "OrderRequest",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PortfolioState",
    "Position",
    "PositionSide",
    "PositionSizeSpec",
    "RiskDecision",
    "RiskDecisionType",
    "RiskPolicy",
    "RiskViolation",
    "Severity",
    "StopLossSpec",
    "StrategyLifecycle",
    "StrategyVersion",
    "SystemState",
    "TakeProfitSpec",
    "TradeProposal",
    "TradingMode",
]
