"""Comprehensive Unit & Integration Tests for Phase 5: Execution Service.

Validates the full safety pipeline (Proposal -> Risk -> Authorization ->
Execution -> Mock Exchange), execution state machine transitions,
idempotency, failure injection handling, timeout recovery, partial fills,
cancellations, and reconciliation.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest

from adapters.database.sqlite import SQLiteManager
from adapters.exchange.mock.adapter import MockExchange
from adapters.repositories.sqlite_repos import (
    AuthorizationRepository,
    BalanceRepository,
    FillRepository,
    OrderRepository,
    PositionRepository,
    StateTransitionRepository,
    SystemEventRepository,
    TradeRepository,
)
from core.domain.enums import (
    ExecutionState,
    MarketRegime,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskDecisionType,
)
from core.domain.order import Order
from core.domain.risk import RiskDecision
from core.domain.trade_proposal import (
    EntrySpec,
    PositionSizeSpec,
    StopLossSpec,
    TakeProfitSpec,
    TradeProposal,
)
from core.errors import (
    DuplicateOrderError,
    ExchangeDisconnectedError,
    ExchangeError,
    ExchangeTimeoutError,
    InvalidStateTransitionError,
    RecordNotFoundError,
)
from core.execution.idempotency import IdempotencyManager
from core.execution.reconciliation import ReconciliationEngine
from core.execution.service import ExecutionService
from core.execution.state_machine import ExecutionStateMachine
from migrations.runner import MigrationRunner

_NOW = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixture Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test_exec.db")


@pytest.fixture
def db(db_path: str) -> Generator[SQLiteManager, None, None]:
    manager = SQLiteManager(db_path, wal_mode=True)
    manager.connect()
    runner = MigrationRunner(manager)
    runner.run()
    yield manager
    manager.close()


@pytest.fixture
def repos(db: SQLiteManager):
    return {
        "order": OrderRepository(db),
        "trade": TradeRepository(db),
        "position": PositionRepository(db),
        "fill": FillRepository(db),
        "auth": AuthorizationRepository(db),
        "state_trans": StateTransitionRepository(db),
        "balance": BalanceRepository(db),
        "system_event": SystemEventRepository(db),
    }


def make_valid_proposal(symbol: str = "BTCUSDT", requested_pct: float = 0.02) -> TradeProposal:
    return TradeProposal(
        proposal_id="PRP-20260829-000001",
        symbol=symbol,
        side=OrderSide.BUY,
        strategy_id="strat_momentum_1",
        strategy_version="1.0.0",
        model_version="hermes-3.5-v1",
        thesis="Breakout test thesis",
        entry=EntrySpec(price=50000.0, order_type=OrderType.LIMIT),
        stop_loss=StopLossSpec(price=47500.0),
        take_profit=TakeProfitSpec(price=55000.0),
        position_size=PositionSizeSpec(requested_pct=requested_pct),
        market_regime=MarketRegime.BULL,
        invalidation_conditions=["Close below 47000"],
        evidence=["Bullish RSI"],
        uncertainty=["CPI data"],
        llm_confidence=0.85,
        created_at=_NOW,
    )


def make_valid_risk_decision(proposal_id: str, decision: RiskDecisionType) -> RiskDecision:
    return RiskDecision(
        decision_id="RD-20260829-000001",
        proposal_id=proposal_id,
        decision=decision,
        violations=[],
        policy_version="1.0",
        timestamp=_NOW,
        computation_ms=1.5,
    )


# ---------------------------------------------------------------------------
# 1. State Machine Tests
# ---------------------------------------------------------------------------


class TestExecutionStateMachine:
    def test_valid_sequential_transitions(self, repos):
        sm = ExecutionStateMachine("TRD-001", "order", repo=repos["state_trans"])
        curr: ExecutionState = sm.current_state
        assert curr == ExecutionState.PROPOSAL_CREATED

        sm.transition_to(ExecutionState.RISK_PENDING)
        curr = sm.current_state
        assert curr == ExecutionState.RISK_PENDING

        sm.transition_to(ExecutionState.APPROVED)
        curr = sm.current_state
        assert curr == ExecutionState.APPROVED

        sm.transition_to(ExecutionState.EXECUTION_PENDING)
        curr = sm.current_state
        assert curr == ExecutionState.EXECUTION_PENDING

        sm.transition_to(ExecutionState.ORDER_SUBMITTED)
        curr = sm.current_state
        assert curr == ExecutionState.ORDER_SUBMITTED

        sm.transition_to(ExecutionState.FILLED)
        curr = sm.current_state
        assert curr == ExecutionState.FILLED

        sm.transition_to(ExecutionState.POSITION_ACTIVE)
        curr = sm.current_state
        assert curr == ExecutionState.POSITION_ACTIVE

        sm.transition_to(ExecutionState.EXIT_PENDING)
        curr = sm.current_state
        assert curr == ExecutionState.EXIT_PENDING

        sm.transition_to(ExecutionState.POSITION_CLOSED)
        curr = sm.current_state
        assert curr == ExecutionState.POSITION_CLOSED

        sm.transition_to(ExecutionState.RECONCILED)
        curr = sm.current_state
        assert curr == ExecutionState.RECONCILED

    def test_invalid_transition_raises_error(self):
        sm = ExecutionStateMachine("TRD-002", "order")
        with pytest.raises(InvalidStateTransitionError):
            sm.transition_to(ExecutionState.FILLED)

    def test_emergency_unknown_path(self):
        sm = ExecutionStateMachine("TRD-003", "order", initial_state=ExecutionState.ORDER_SUBMITTED)
        # Any state -> UNKNOWN
        sm.transition_to(ExecutionState.UNKNOWN)
        curr: ExecutionState = sm.current_state
        assert curr == ExecutionState.UNKNOWN

        # UNKNOWN -> FREEZE -> RECONCILING -> RESOLVED
        sm.transition_to(ExecutionState.FREEZE)
        curr = sm.current_state
        assert curr == ExecutionState.FREEZE

        sm.transition_to(ExecutionState.RECONCILING)
        curr = sm.current_state
        assert curr == ExecutionState.RECONCILING

        sm.transition_to(ExecutionState.RESOLVED)
        curr = sm.current_state
        assert curr == ExecutionState.RESOLVED

    def test_risk_rejected_vs_exchange_rejected(self):
        sm_risk = ExecutionStateMachine(
            "TRD-004", "order", initial_state=ExecutionState.RISK_PENDING
        )
        sm_risk.transition_to(ExecutionState.RISK_REJECTED)
        s_risk: ExecutionState = sm_risk.current_state
        assert s_risk == ExecutionState.RISK_REJECTED

        sm_ex = ExecutionStateMachine(
            "TRD-005", "order", initial_state=ExecutionState.ORDER_SUBMITTED
        )
        sm_ex.transition_to(ExecutionState.EXCHANGE_REJECTED)
        s_ex: ExecutionState = sm_ex.current_state
        assert s_ex == ExecutionState.EXCHANGE_REJECTED
        assert s_risk.value != s_ex.value


# ---------------------------------------------------------------------------
# 2. Idempotency Tests
# ---------------------------------------------------------------------------


class TestIdempotencyManager:
    def test_client_order_id_generation_format(self):
        mgr = IdempotencyManager()
        cid1 = mgr.generate_client_order_id(date=_NOW)
        cid2 = mgr.generate_client_order_id(date=_NOW)

        assert cid1.startswith("TRD-20260829-")
        assert cid2.startswith("TRD-20260829-")
        assert cid1 != cid2

    def test_duplicate_submission_in_memory_blocked(self):
        mgr = IdempotencyManager()
        cid = mgr.generate_client_order_id(date=_NOW)
        mgr.check_and_register(cid)

        with pytest.raises(DuplicateOrderError):
            mgr.check_and_register(cid)

    def test_duplicate_submission_in_sqlite_blocked(self, repos):
        cid = "TRD-20260829-999999"

        order = Order(
            client_order_id=cid,
            proposal_id="PRP-20260829-000001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            created_at=_NOW,
            updated_at=_NOW,
        )
        repos["order"].save_order(order)

        # Fresh manager without in-memory cache should still block via SQLite
        fresh_mgr = IdempotencyManager()
        with pytest.raises(DuplicateOrderError):
            fresh_mgr.check_and_register(cid, order_repo=repos["order"])


# ---------------------------------------------------------------------------
# 3. Mock Exchange Failure Mode Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMockExchangeFailures:
    async def test_filled_mode(self):
        mock = MockExchange(default_fill_mode="FILLED")
        order = Order(
            client_order_id="TRD-001",
            proposal_id="PRP-1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.5,
            price=50000.0,
            created_at=_NOW,
            updated_at=_NOW,
        )
        res = await mock.submit_order(order)
        assert res.status == OrderStatus.FILLED
        assert res.filled_quantity == 0.5

    async def test_partial_fill_mode(self):
        mock = MockExchange(default_fill_mode="PARTIAL_FILL")
        order = Order(
            client_order_id="TRD-002",
            proposal_id="PRP-1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            created_at=_NOW,
            updated_at=_NOW,
        )
        res = await mock.submit_order(order)
        assert res.status == OrderStatus.PARTIAL
        assert res.filled_quantity == 0.5

    async def test_rejected_mode(self):
        mock = MockExchange(default_fill_mode="REJECTED")
        order = Order(
            client_order_id="TRD-003",
            proposal_id="PRP-1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            created_at=_NOW,
            updated_at=_NOW,
        )
        with pytest.raises(ExchangeError, match="Insufficient margin"):
            await mock.submit_order(order)

    async def test_timeout_mode(self):
        mock = MockExchange(default_fill_mode="TIMEOUT")
        order = Order(
            client_order_id="TRD-004",
            proposal_id="PRP-1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            created_at=_NOW,
            updated_at=_NOW,
        )
        with pytest.raises(ExchangeTimeoutError):
            await mock.submit_order(order)

        # Confirm order was received on mock exchange despite timeout
        query_res = await mock.get_order("TRD-004")
        assert query_res.client_order_id == "TRD-004"

    async def test_network_error_mode(self):
        mock = MockExchange(default_fill_mode="NETWORK_ERROR")
        order = Order(
            client_order_id="TRD-005",
            proposal_id="PRP-1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            created_at=_NOW,
            updated_at=_NOW,
        )
        with pytest.raises(ExchangeDisconnectedError):
            await mock.submit_order(order)

    async def test_unknown_order_mode(self):
        mock = MockExchange(default_fill_mode="UNKNOWN_ORDER")
        with pytest.raises(RecordNotFoundError):
            await mock.get_order("NON_EXISTENT")

    async def test_cancelled_mode(self):
        mock = MockExchange(default_fill_mode="FILLED")
        order = Order(
            client_order_id="TRD-006",
            proposal_id="PRP-1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            created_at=_NOW,
            updated_at=_NOW,
        )
        await mock.submit_order(order)
        cancelled = await mock.cancel_order("TRD-006")
        assert cancelled is True

    async def test_duplicate_request_mode(self):
        mock = MockExchange()
        order = Order(
            client_order_id="TRD-007",
            proposal_id="PRP-1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            created_at=_NOW,
            updated_at=_NOW,
        )
        await mock.submit_order(order)
        with pytest.raises(ExchangeError, match="Duplicate client order ID"):
            await mock.submit_order(order)


# ---------------------------------------------------------------------------
# 4. Execution Service End-to-End & Recovery Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExecutionServicePipeline:
    async def test_successful_execution_pipeline(self, repos):
        mock_exchange = MockExchange(default_fill_mode="FILLED")
        svc = ExecutionService(
            exchange=mock_exchange,
            order_repo=repos["order"],
            trade_repo=repos["trade"],
            position_repo=repos["position"],
            fill_repo=repos["fill"],
            auth_repo=repos["auth"],
            state_transition_repo=repos["state_trans"],
        )

        proposal = make_valid_proposal()
        risk_decision = make_valid_risk_decision(proposal.proposal_id, RiskDecisionType.APPROVED)

        result = await svc.execute_proposal(proposal, risk_decision)

        assert result.success is True
        assert result.execution_state == ExecutionState.POSITION_ACTIVE
        assert result.order is not None
        assert result.position is not None

        # Verify authorization recorded in SQLite
        auths = repos["auth"].get_by_proposal(proposal.proposal_id)
        assert len(auths) == 1
        assert auths[0]["authorized_by"] == "risk_engine"

        # Verify order saved in SQLite
        db_order = repos["order"].get_by_id(result.client_order_id)
        assert db_order is not None
        assert db_order.status == OrderStatus.FILLED

    async def test_execution_rejected_when_risk_not_approved(self, repos):
        mock_exchange = MockExchange()
        svc = ExecutionService(
            exchange=mock_exchange,
            order_repo=repos["order"],
            trade_repo=repos["trade"],
            position_repo=repos["position"],
            fill_repo=repos["fill"],
            auth_repo=repos["auth"],
            state_transition_repo=repos["state_trans"],
        )

        proposal = make_valid_proposal()
        risk_decision = make_valid_risk_decision(proposal.proposal_id, RiskDecisionType.REJECTED)

        result = await svc.execute_proposal(proposal, risk_decision)

        assert result.success is False
        assert result.execution_state == ExecutionState.RISK_REJECTED

    async def test_timeout_recovery_protocol_order_found(self, repos):
        """Required recovery pattern test: submit -> timeout -> query exchange -> reconcile."""
        mock_exchange = MockExchange(default_fill_mode="TIMEOUT")
        svc = ExecutionService(
            exchange=mock_exchange,
            order_repo=repos["order"],
            trade_repo=repos["trade"],
            position_repo=repos["position"],
            fill_repo=repos["fill"],
            auth_repo=repos["auth"],
            state_transition_repo=repos["state_trans"],
        )

        proposal = make_valid_proposal()
        risk_decision = make_valid_risk_decision(proposal.proposal_id, RiskDecisionType.APPROVED)

        result = await svc.execute_proposal(proposal, risk_decision)

        # Must NOT re-submit blindly! Must query, reconcile, and reach RESOLVED state
        assert result.execution_state == ExecutionState.RESOLVED
        assert result.order is not None

    async def test_timeout_recovery_protocol_order_missing(self, repos):
        """Timeout occurs before order reaches exchange."""

        # Create a mock exchange that raises timeout on submit and RecordNotFoundError on query
        class TimeoutMissingMock(MockExchange):
            async def submit_order(self, order: Order) -> Order:
                raise ExchangeTimeoutError("Timeout before receipt")

            async def get_order(self, order_id: str) -> Order:
                raise RecordNotFoundError("Order missing on exchange")

        mock_exchange = TimeoutMissingMock()
        svc = ExecutionService(
            exchange=mock_exchange,
            order_repo=repos["order"],
            trade_repo=repos["trade"],
            position_repo=repos["position"],
            fill_repo=repos["fill"],
            auth_repo=repos["auth"],
            state_transition_repo=repos["state_trans"],
        )

        proposal = make_valid_proposal()
        risk_decision = make_valid_risk_decision(proposal.proposal_id, RiskDecisionType.APPROVED)

        result = await svc.execute_proposal(proposal, risk_decision)

        assert result.execution_state == ExecutionState.RESOLVED
        assert result.success is False
        assert "timed out before reaching exchange" in (result.error_message or "")


# ---------------------------------------------------------------------------
# 5. Reconciliation Engine Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReconciliationEngine:
    async def test_reconciliation_order_self_healing(self, repos):
        mock_exchange = MockExchange(default_fill_mode="FILLED")

        # Save order as SUBMITTED locally in SQLite, while exchange shows it as FILLED
        order = Order(
            client_order_id="TRD-20260829-000100",
            proposal_id="PRP-100",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            status=OrderStatus.SUBMITTED,
            created_at=_NOW,
            updated_at=_NOW,
        )
        repos["order"].save_order(order)
        await mock_exchange.submit_order(order)

        recon = ReconciliationEngine(
            exchange=mock_exchange,
            order_repo=repos["order"],
            position_repo=repos["position"],
            balance_repo=repos["balance"],
            system_event_repo=repos["system_event"],
        )

        report = await recon.reconcile()
        assert report is not None

        # Local order status should be updated to FILLED automatically
        updated_local_order = repos["order"].get_by_id("TRD-20260829-000100")
        assert updated_local_order.status == OrderStatus.FILLED
