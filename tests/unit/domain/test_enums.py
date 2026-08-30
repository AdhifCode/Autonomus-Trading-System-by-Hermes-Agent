"""Tests for core.domain.enums — enum completeness and serialization.

Verifies every enum has the expected members, serializes to/from strings,
and matches the implementation_spec.md §1 definitions.
"""

from __future__ import annotations

import pytest

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

# ---------------------------------------------------------------------------
# TradingMode
# ---------------------------------------------------------------------------

_TRADING_MODE_EXPECTED = frozenset(
    {
        "DEVELOPMENT",
        "BACKTEST",
        "SHADOW",
        "PAPER",
        "TESTNET",
        "LIMITED_LIVE",
        "LIVE",
    }
)


class TestTradingMode:
    """Tests for TradingMode enum."""

    def test_completeness(self):
        assert {m.value for m in TradingMode} == _TRADING_MODE_EXPECTED

    def test_member_count(self):
        assert len(TradingMode) == 7

    def test_string_value(self):
        assert TradingMode.DEVELOPMENT == "DEVELOPMENT"
        assert TradingMode.LIVE == "LIVE"

    def test_from_string(self):
        assert TradingMode("PAPER") is TradingMode.PAPER

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            TradingMode("INVALID_MODE")

    def test_is_str(self):
        """StrEnum values must be valid str instances."""
        assert isinstance(TradingMode.DEVELOPMENT, str)


# ---------------------------------------------------------------------------
# OrderSide
# ---------------------------------------------------------------------------


class TestOrderSide:
    """Tests for OrderSide enum."""

    def test_completeness(self):
        assert {m.value for m in OrderSide} == {"BUY", "SELL"}

    def test_member_count(self):
        assert len(OrderSide) == 2

    def test_from_string(self):
        assert OrderSide("BUY") is OrderSide.BUY
        assert OrderSide("SELL") is OrderSide.SELL

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            OrderSide("HOLD")


# ---------------------------------------------------------------------------
# OrderType
# ---------------------------------------------------------------------------

_ORDER_TYPE_EXPECTED = frozenset({"MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"})


class TestOrderType:
    """Tests for OrderType enum."""

    def test_completeness(self):
        assert {m.value for m in OrderType} == _ORDER_TYPE_EXPECTED

    def test_member_count(self):
        assert len(OrderType) == 4

    def test_from_string(self):
        assert OrderType("STOP_LIMIT") is OrderType.STOP_LIMIT

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            OrderType("TRAILING_STOP")


# ---------------------------------------------------------------------------
# OrderStatus
# ---------------------------------------------------------------------------

_ORDER_STATUS_EXPECTED = frozenset(
    {
        "PENDING",
        "SUBMITTED",
        "PARTIAL",
        "FILLED",
        "CANCELLED",
        "REJECTED",
        "EXPIRED",
    }
)


class TestOrderStatus:
    """Tests for OrderStatus enum."""

    def test_completeness(self):
        assert {m.value for m in OrderStatus} == _ORDER_STATUS_EXPECTED

    def test_member_count(self):
        assert len(OrderStatus) == 7


# ---------------------------------------------------------------------------
# PositionSide
# ---------------------------------------------------------------------------


class TestPositionSide:
    """Tests for PositionSide enum."""

    def test_completeness(self):
        assert {m.value for m in PositionSide} == {"LONG", "SHORT"}

    def test_member_count(self):
        assert len(PositionSide) == 2


# ---------------------------------------------------------------------------
# MarketRegime
# ---------------------------------------------------------------------------

_MARKET_REGIME_EXPECTED = frozenset(
    {
        "BULL",
        "BEAR",
        "SIDEWAYS",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
    }
)


class TestMarketRegime:
    """Tests for MarketRegime enum — architecture §22."""

    def test_completeness(self):
        assert {m.value for m in MarketRegime} == _MARKET_REGIME_EXPECTED

    def test_member_count(self):
        assert len(MarketRegime) == 5

    def test_from_string(self):
        assert MarketRegime("HIGH_VOLATILITY") is MarketRegime.HIGH_VOLATILITY


# ---------------------------------------------------------------------------
# RiskDecisionType
# ---------------------------------------------------------------------------

_RISK_DECISION_EXPECTED = frozenset({"APPROVED", "REJECTED", "FREEZE"})


class TestRiskDecisionType:
    """Tests for RiskDecisionType enum."""

    def test_completeness(self):
        assert {m.value for m in RiskDecisionType} == _RISK_DECISION_EXPECTED

    def test_member_count(self):
        assert len(RiskDecisionType) == 3


# ---------------------------------------------------------------------------
# ExecutionState
# ---------------------------------------------------------------------------

_EXECUTION_STATE_EXPECTED = frozenset(
    {
        "PROPOSAL_CREATED",
        "RISK_PENDING",
        "RISK_REJECTED",
        "APPROVED",
        "EXECUTION_PENDING",
        "ORDER_SUBMITTED",
        "EXCHANGE_REJECTED",
        "PARTIAL",
        "FILLED",
        "POSITION_ACTIVE",
        "EXIT_PENDING",
        "POSITION_CLOSED",
        "RECONCILED",
        "UNKNOWN",
        "FREEZE",
        "RECONCILING",
        "RESOLVED",
    }
)


class TestExecutionState:
    """Tests for ExecutionState enum — implementation_spec §5."""

    def test_completeness(self):
        assert {m.value for m in ExecutionState} == _EXECUTION_STATE_EXPECTED

    def test_member_count(self):
        assert len(ExecutionState) == 17

    def test_risk_rejected_distinct(self):
        """RISK_REJECTED and EXCHANGE_REJECTED must be distinct (AI_ENGINEERING_RULES §4a)."""
        assert ExecutionState.RISK_REJECTED != ExecutionState.EXCHANGE_REJECTED
        assert ExecutionState.RISK_REJECTED.value == "RISK_REJECTED"
        assert ExecutionState.EXCHANGE_REJECTED.value == "EXCHANGE_REJECTED"

    def test_emergency_states_present(self):
        """Emergency path states must exist: UNKNOWN, FREEZE, RECONCILING, RESOLVED."""
        emergency = {
            ExecutionState.UNKNOWN,
            ExecutionState.FREEZE,
            ExecutionState.RECONCILING,
            ExecutionState.RESOLVED,
        }
        assert emergency.issubset(set(ExecutionState))


# ---------------------------------------------------------------------------
# StrategyLifecycle
# ---------------------------------------------------------------------------

_STRATEGY_LIFECYCLE_EXPECTED = frozenset(
    {
        "IDEA",
        "RESEARCH",
        "CANDIDATE",
        "BACKTEST",
        "VALIDATED",
        "PAPER",
        "APPROVED",
        "PRODUCTION",
        "DEPRECATED",
    }
)


class TestStrategyLifecycle:
    """Tests for StrategyLifecycle enum — architecture §20."""

    def test_completeness(self):
        assert {m.value for m in StrategyLifecycle} == _STRATEGY_LIFECYCLE_EXPECTED

    def test_member_count(self):
        assert len(StrategyLifecycle) == 9


# ---------------------------------------------------------------------------
# KillSwitchState
# ---------------------------------------------------------------------------

_KILL_SWITCH_EXPECTED = frozenset({"ACTIVE", "SOFT_KILL", "HARD_KILL"})


class TestKillSwitchState:
    """Tests for KillSwitchState enum — architecture §30."""

    def test_completeness(self):
        assert {m.value for m in KillSwitchState} == _KILL_SWITCH_EXPECTED

    def test_member_count(self):
        assert len(KillSwitchState) == 3


# ---------------------------------------------------------------------------
# EventType
# ---------------------------------------------------------------------------

_EVENT_TYPE_EXPECTED = frozenset(
    {
        "TRADE_PROPOSED",
        "RISK_EVALUATED",
        "ORDER_SUBMITTED",
        "ORDER_FILLED",
        "ORDER_REJECTED",
        "POSITION_OPENED",
        "POSITION_CLOSED",
        "KILL_SWITCH_ACTIVATED",
        "RECONCILIATION_STARTED",
        "RECONCILIATION_COMPLETED",
        "STATE_TRANSITION",
        "SYSTEM_ERROR",
        "DATA_STALE",
        "EXCHANGE_DISCONNECTED",
        "HERMES_TOOL_DISPATCHED",
        "HERMES_PROPOSAL_RECEIVED",
    }
)


class TestEventType:
    """Tests for EventType enum — implementation_spec §10."""

    def test_completeness(self):
        assert {m.value for m in EventType} == _EVENT_TYPE_EXPECTED

    def test_member_count(self):
        assert len(EventType) == 16


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

_SEVERITY_EXPECTED = frozenset({"INFO", "WARNING", "ERROR", "CRITICAL"})


class TestSeverity:
    """Tests for Severity enum."""

    def test_completeness(self):
        assert {m.value for m in Severity} == _SEVERITY_EXPECTED

    def test_member_count(self):
        assert len(Severity) == 4


# ---------------------------------------------------------------------------
# Cross-cutting: all enums are StrEnum
# ---------------------------------------------------------------------------


ALL_ENUMS = [
    TradingMode,
    OrderSide,
    OrderType,
    OrderStatus,
    PositionSide,
    MarketRegime,
    RiskDecisionType,
    ExecutionState,
    StrategyLifecycle,
    KillSwitchState,
    EventType,
    Severity,
]


@pytest.mark.parametrize("enum_cls", ALL_ENUMS, ids=lambda e: e.__name__)
def test_all_enums_are_str(enum_cls):
    """Every enum value must be a plain str (StrEnum)."""
    for member in enum_cls:
        assert isinstance(member, str)
        assert member == member.value
