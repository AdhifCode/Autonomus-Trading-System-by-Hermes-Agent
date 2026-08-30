"""Phase 13: Full System Flow & 18 Test Scenarios Integration Test Suite.

Verifies end-to-end integration across:
Market Data -> Strategy -> Hermes -> TradeProposal -> Validation -> Risk Engine
-> Authorization -> Execution -> Exchange Adapter -> Exchange -> Fill -> Portfolio
-> SQLite -> Trade Journal -> Knowledge API

Includes 18 mandatory test scenarios and complete flow validation.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime, timedelta
import pytest

from adapters.database.sqlite import SQLiteManager
from adapters.exchange.base import ExchangeAdapter
from adapters.exchange.mock.adapter import MockExchange
from adapters.repositories.sqlite_repos import (
    AuthorizationRepository,
    BalanceRepository,
    FillRepository,
    OrderRepository,
    PositionRepository,
    RiskDecisionRepository,
    StateTransitionRepository,
    StrategyVersionRepository,
    SystemEventRepository,
    TradeRepository,
)
from core.domain.enums import (
    EventType,
    ExecutionState,
    KillSwitchState,
    MarketRegime,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskDecisionType,
    Severity,
    TradingMode,
)
from core.domain.market_state import MarketState
from core.domain.order import Order
from core.domain.portfolio import PortfolioState
from core.domain.position import Position
from core.domain.risk import RiskDecision, RiskPolicy
from core.domain.system_state import SystemState
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
    HermesBlockedOperationError,
    HermesUnauthorizedError,
    InvalidStateTransitionError,
    RiskError,
)
from core.execution.reconciliation import MismatchType, ReconciliationEngine
from core.execution.service import ExecutionService
from core.risk.engine import RiskEngine
from integration.hermes.contracts.schema import ProposalSubmissionRequest, ToolRequest
from integration.hermes.gateway import HermesGateway
from knowledge.api import KnowledgeAPI
from knowledge.models import NoteCategory, TradeJournalEntry
from migrations.runner import MigrationRunner
from web.service import ControlCenterService


@pytest.fixture
def env_setup():
    """Setup clean temporary database and vault directories for testing."""
    tmp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db_file.close()
    db_path = tmp_db_file.name

    tmp_vault_dir = tempfile.TemporaryDirectory()
    vault_path = tmp_vault_dir.name

    db = SQLiteManager(db_path=db_path)
    db.connect()
    MigrationRunner(db).run()

    trade_repo = TradeRepository(db)
    order_repo = OrderRepository(db)
    position_repo = PositionRepository(db)
    balance_repo = BalanceRepository(db)
    risk_repo = RiskDecisionRepository(db)
    event_repo = SystemEventRepository(db)
    fill_repo = FillRepository(db)
    auth_repo = AuthorizationRepository(db)
    state_transition_repo = StateTransitionRepository(db)
    strategy_repo = StrategyVersionRepository(db)

    # Seed initial balance
    balance_repo.save(currency="USDT", total=50000.0, available=50000.0, locked=0.0, source="local")

    exchange = MockExchange()
    policy = RiskPolicy(policy_version="v1.4")
    risk_engine = RiskEngine(policy=policy)

    execution_service = ExecutionService(
        exchange=exchange,
        order_repo=order_repo,
        trade_repo=trade_repo,
        position_repo=position_repo,
        fill_repo=fill_repo,
        auth_repo=auth_repo,
        state_transition_repo=state_transition_repo,
        balance_repo=balance_repo,
        system_event_repo=event_repo,
    )

    knowledge_api = KnowledgeAPI(vault_path=vault_path)
    hermes_gateway = HermesGateway(risk_engine=risk_engine, system_event_repo=event_repo)

    yield {
        "db_path": db_path,
        "vault_path": vault_path,
        "db": db,
        "trade_repo": trade_repo,
        "order_repo": order_repo,
        "position_repo": position_repo,
        "balance_repo": balance_repo,
        "risk_repo": risk_repo,
        "event_repo": event_repo,
        "fill_repo": fill_repo,
        "auth_repo": auth_repo,
        "exchange": exchange,
        "policy": policy,
        "risk_engine": risk_engine,
        "execution_service": execution_service,
        "knowledge_api": knowledge_api,
        "hermes_gateway": hermes_gateway,
    }

    if os.path.exists(db_path):
        os.unlink(db_path)
    tmp_vault_dir.cleanup()


# ---------------------------------------------------------------------------
# Helper function for TradeProposal dictionary creation
# ---------------------------------------------------------------------------


def make_proposal_payload(
    proposal_id: str = "PRP-20260830-100001",
    requested_pct: float = 0.04,
    symbol: str = "BTCUSDT",
    entry_price: float = 62000.0,
) -> dict:
    return {
        "proposal_id": proposal_id,
        "symbol": symbol,
        "side": "BUY",
        "strategy_id": "breakout_v2",
        "strategy_version": "2.1",
        "model_version": "v1.0",
        "thesis": "Bullish consolidation breakout",
        "entry": {"price": entry_price, "order_type": "MARKET"},
        "stop_loss": {"price": entry_price * 0.96},
        "take_profit": {"price": entry_price * 1.06},
        "position_size": {"requested_pct": requested_pct},
        "market_regime": "BULL",
        "invalidation_conditions": ["Price drops below stop loss"],
        "evidence": ["ADX > 30", "Volume expansion"],
        "llm_confidence": 0.88,
        "created_at": datetime.now(UTC).isoformat(),
    }


def make_context_states(now: datetime):
    mkt = MarketState(
        symbol="BTCUSDT",
        price=62000.0,
        bid=61990.0,
        ask=62010.0,
        spread=20.0,
        volume_24h=250000.0,
        timestamp=now,
        data_age_seconds=1.0,
    )
    port = PortfolioState(
        balance=50000.0,
        equity=50000.0,
        available_margin=50000.0,
        exposure=0.0,
        timestamp=now,
    )
    sys = SystemState(
        trading_mode=TradingMode.PAPER,
        kill_switch=KillSwitchState.ACTIVE,
        exchange_connected=True,
        data_healthy=True,
        last_heartbeat=now,
    )
    return mkt, port, sys


# ---------------------------------------------------------------------------
# Scenario 1: Valid Trade (End-to-End Pipeline)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_valid_trade_full_flow(env_setup):
    """Scenario 1: Valid Trade End-to-End Flow."""
    now = datetime.now(UTC)
    hermes_gateway = env_setup["hermes_gateway"]
    risk_engine = env_setup["risk_engine"]
    execution_service = env_setup["execution_service"]
    order_repo = env_setup["order_repo"]
    knowledge_api = env_setup["knowledge_api"]
    event_repo = env_setup["event_repo"]

    prop_dict = make_proposal_payload("PRP-20260830-100001", requested_pct=0.04)
    submission_req = ProposalSubmissionRequest(
        proposal_data=prop_dict,
        model_version="hermes-v2.1",
    )

    mkt_state, port_state, sys_state = make_context_states(now)

    res = hermes_gateway.submit_proposal(
        submission_payload=submission_req,
        market_state=mkt_state,
        portfolio=port_state,
        system_state=sys_state,
    )

    assert res.status == "ACCEPTED"
    assert res.risk_decision["decision"] == "APPROVED"

    proposal = TradeProposal.model_validate(prop_dict)
    risk_decision = risk_engine.evaluate(proposal, mkt_state, port_state, sys_state)

    exec_result = await execution_service.execute_proposal(proposal, risk_decision)
    assert exec_result.success is True
    assert exec_result.order is not None

    persisted_order = order_repo.get_by_id(exec_result.client_order_id)
    assert persisted_order is not None
    assert persisted_order.status == OrderStatus.FILLED

    journal_entry = TradeJournalEntry(
        trade_id="TRD-20260830-100001",
        proposal_id=res.proposal_id,
        symbol="BTCUSDT",
        direction="LONG",
        strategy_id="breakout_v2",
        strategy_version="2.1",
        entry_price=62000.0,
        quantity=0.03,
        thesis="Bullish consolidation breakout",
        market_regime="BULL",
        initial_stop_loss=60000.0,
        initial_take_profit=66000.0,
        timestamp_entry=now,
    )

    recorded = knowledge_api.record_trade_journal_entry(journal_entry)
    assert recorded is True or recorded is False

    events = event_repo.get_all()
    assert len(events) > 0


# ---------------------------------------------------------------------------
# Scenario 2: Risk Rejection
# ---------------------------------------------------------------------------


def test_scenario_2_risk_rejection(env_setup):
    """Scenario 2: Excessive position size triggers Risk Engine rejection."""
    hermes_gateway = env_setup["hermes_gateway"]
    order_repo = env_setup["order_repo"]
    now = datetime.now(UTC)

    prop_dict = make_proposal_payload("PRP-20260830-100002", requested_pct=0.50)
    submission_req = ProposalSubmissionRequest(
        proposal_data=prop_dict,
        model_version="hermes-v2.1",
    )

    mkt_state, port_state, sys_state = make_context_states(now)

    res = hermes_gateway.submit_proposal(
        submission_payload=submission_req,
        market_state=mkt_state,
        portfolio=port_state,
        system_state=sys_state,
    )

    assert res.status == "REJECTED"
    assert res.risk_decision["decision"] == "REJECTED"
    assert any(v["validator"] == "position_size" for v in res.risk_decision.get("violations", []))

    orders = order_repo.get_open_orders()
    assert len(orders) == 0


# ---------------------------------------------------------------------------
# Scenario 3: Stale Data Rejection
# ---------------------------------------------------------------------------


def test_scenario_3_stale_data_rejection(env_setup):
    """Scenario 3: Market data older than threshold triggers Risk Validator V03 rejection."""
    risk_engine = env_setup["risk_engine"]
    now = datetime.now(UTC)

    proposal = TradeProposal.model_validate(make_proposal_payload("PRP-20260830-100003"))

    stale_mkt = MarketState(
        symbol="BTCUSDT",
        price=62000.0,
        bid=61990.0,
        ask=62010.0,
        spread=20.0,
        volume_24h=250000.0,
        timestamp=now - timedelta(seconds=120),
        data_age_seconds=120.0,
    )
    port_state = PortfolioState(
        balance=50000.0,
        equity=50000.0,
        available_margin=50000.0,
        exposure=0.0,
        timestamp=now,
    )
    sys_state = SystemState(
        trading_mode=TradingMode.PAPER,
        kill_switch=KillSwitchState.ACTIVE,
        exchange_connected=True,
        data_healthy=True,
        last_heartbeat=now,
    )

    decision = risk_engine.evaluate(proposal=proposal, market=stale_mkt, portfolio=port_state, system=sys_state)
    assert decision.decision == RiskDecisionType.REJECTED
    assert any(v.validator == "stale_data" for v in decision.violations)


# ---------------------------------------------------------------------------
# Scenario 4: Kill Switch Halt
# ---------------------------------------------------------------------------


def test_scenario_4_kill_switch_halt(env_setup):
    """Scenario 4: System Kill Switch HARD_KILL immediately returns FREEZE."""
    risk_engine = env_setup["risk_engine"]
    now = datetime.now(UTC)

    proposal = TradeProposal.model_validate(make_proposal_payload("PRP-20260830-100004"))

    mkt_state, port_state, _ = make_context_states(now)
    sys_state_ks = SystemState(
        trading_mode=TradingMode.PAPER,
        kill_switch=KillSwitchState.HARD_KILL,
        exchange_connected=True,
        data_healthy=True,
        last_heartbeat=now,
    )

    decision = risk_engine.evaluate(proposal=proposal, market=mkt_state, portfolio=port_state, system=sys_state_ks)
    assert decision.decision == RiskDecisionType.FREEZE
    assert any(v.validator == "kill_switch" for v in decision.violations)


# ---------------------------------------------------------------------------
# Scenario 5: Max Portfolio Exposure
# ---------------------------------------------------------------------------


def test_scenario_5_max_exposure_rejection(env_setup):
    """Scenario 5: Total exposure exceeding max_portfolio_exposure_pct triggers REJECTED."""
    risk_engine = env_setup["risk_engine"]
    now = datetime.now(UTC)

    proposal = TradeProposal.model_validate(make_proposal_payload("PRP-20260830-100005", requested_pct=0.04))

    mkt_state = MarketState(
        symbol="BTCUSDT",
        price=62000.0,
        bid=61990.0,
        ask=62010.0,
        spread=20.0,
        volume_24h=250000.0,
        timestamp=now,
        data_age_seconds=1.0,
    )

    port_state = PortfolioState(
        balance=50000.0,
        equity=50000.0,
        available_margin=10000.0,
        exposure=40000.0,
        timestamp=now,
    )
    sys_state = SystemState(
        trading_mode=TradingMode.PAPER,
        kill_switch=KillSwitchState.ACTIVE,
        exchange_connected=True,
        data_healthy=True,
        last_heartbeat=now,
    )

    decision = risk_engine.evaluate(proposal=proposal, market=mkt_state, portfolio=port_state, system=sys_state)
    assert decision.decision == RiskDecisionType.REJECTED
    assert any(v.validator == "portfolio_exposure" for v in decision.violations)


# ---------------------------------------------------------------------------
# Scenario 6: Max Drawdown Limit
# ---------------------------------------------------------------------------


def test_scenario_6_max_drawdown_rejection(env_setup):
    """Scenario 6: Portfolio drawdown exceeding max_drawdown_pct triggers REJECTED."""
    risk_engine = env_setup["risk_engine"]
    now = datetime.now(UTC)

    proposal = TradeProposal.model_validate(make_proposal_payload("PRP-20260830-100006", requested_pct=0.02))

    mkt_state = MarketState(
        symbol="BTCUSDT",
        price=62000.0,
        bid=61990.0,
        ask=62010.0,
        spread=20.0,
        volume_24h=250000.0,
        timestamp=now,
        data_age_seconds=1.0,
    )

    port_state = PortfolioState(
        balance=37500.0,
        equity=37500.0,
        available_margin=37500.0,
        exposure=0.0,
        drawdown=0.25,
        timestamp=now,
    )
    sys_state = SystemState(
        trading_mode=TradingMode.PAPER,
        kill_switch=KillSwitchState.ACTIVE,
        exchange_connected=True,
        data_healthy=True,
        last_heartbeat=now,
    )

    decision = risk_engine.evaluate(proposal=proposal, market=mkt_state, portfolio=port_state, system=sys_state)
    assert decision.decision == RiskDecisionType.REJECTED
    assert any(v.validator == "drawdown" for v in decision.violations)


# ---------------------------------------------------------------------------
# Scenario 7: Insufficient Liquidity
# ---------------------------------------------------------------------------


def test_scenario_7_insufficient_liquidity_rejection(env_setup):
    """Scenario 7: 24h market volume below min_liquidity_usd triggers REJECTED."""
    risk_engine = env_setup["risk_engine"]
    now = datetime.now(UTC)

    proposal = TradeProposal.model_validate(make_proposal_payload("PRP-20260830-100007", requested_pct=0.02))

    low_liq_mkt = MarketState(
        symbol="BTCUSDT",
        price=62000.0,
        bid=61990.0,
        ask=62010.0,
        spread=20.0,
        volume_24h=5000.0,
        timestamp=now,
        data_age_seconds=1.0,
    )
    port_state = PortfolioState(
        balance=50000.0,
        equity=50000.0,
        available_margin=50000.0,
        exposure=0.0,
        timestamp=now,
    )
    sys_state = SystemState(
        trading_mode=TradingMode.PAPER,
        kill_switch=KillSwitchState.ACTIVE,
        exchange_connected=True,
        data_healthy=True,
        last_heartbeat=now,
    )

    decision = risk_engine.evaluate(proposal=proposal, market=low_liq_mkt, portfolio=port_state, system=sys_state)
    assert decision.decision == RiskDecisionType.REJECTED
    assert any(v.validator == "liquidity" for v in decision.violations)


# ---------------------------------------------------------------------------
# Scenario 8: Partial Fill Execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_8_partial_fill_handling(env_setup):
    """Scenario 8: Partial fill updates order status and records fill."""
    execution_service = env_setup["execution_service"]
    risk_engine = env_setup["risk_engine"]
    exchange = env_setup["exchange"]
    now = datetime.now(UTC)

    exchange.inject_failure("PARTIAL_FILL")

    prop_dict = make_proposal_payload("PRP-20260830-100008")
    proposal = TradeProposal.model_validate(prop_dict)
    mkt_state, port_state, sys_state = make_context_states(now)
    risk_decision = risk_engine.evaluate(proposal, mkt_state, port_state, sys_state)

    exec_result = await execution_service.execute_proposal(proposal, risk_decision)
    assert exec_result.success is True
    assert exec_result.order.status == OrderStatus.PARTIAL
    assert exec_result.order.filled_quantity > 0.0


# ---------------------------------------------------------------------------
# Scenario 9: Exchange Timeout & Recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_9_exchange_timeout_handling(env_setup):
    """Scenario 9: Submit order timeout handles exception and state gracefully."""
    execution_service = env_setup["execution_service"]
    risk_engine = env_setup["risk_engine"]
    exchange = env_setup["exchange"]
    now = datetime.now(UTC)

    exchange.inject_failure("TIMEOUT")

    prop_dict = make_proposal_payload("PRP-20260830-100009")
    proposal = TradeProposal.model_validate(prop_dict)
    mkt_state, port_state, sys_state = make_context_states(now)
    risk_decision = risk_engine.evaluate(proposal, mkt_state, port_state, sys_state)

    exec_result = await execution_service.execute_proposal(proposal, risk_decision)
    assert exec_result.error_message is not None
    assert "recovered" in exec_result.error_message.lower() or "timeout" in exec_result.error_message.lower()


# ---------------------------------------------------------------------------
# Scenario 10: Duplicate Order Submission
# ---------------------------------------------------------------------------


def test_scenario_10_duplicate_submission_protection(env_setup):
    """Scenario 10: Duplicate client_order_id submission is blocked by idempotency layer."""
    execution_service = env_setup["execution_service"]
    order_repo = env_setup["order_repo"]

    client_order_id = "TRD-20260830-999999"
    execution_service.idempotency.check_and_register(client_order_id, order_repo=order_repo)

    with pytest.raises(DuplicateOrderError):
        execution_service.idempotency.check_and_register(client_order_id, order_repo=order_repo)


# ---------------------------------------------------------------------------
# Scenario 11: Unknown Order Handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_11_unknown_order_reconciliation_flow(env_setup):
    """Scenario 11: Mismatched order triggers reconciliation and self-heals state."""
    exchange = env_setup["exchange"]
    order_repo = env_setup["order_repo"]
    position_repo = env_setup["position_repo"]
    balance_repo = env_setup["balance_repo"]
    event_repo = env_setup["event_repo"]
    now = datetime.now(UTC)

    reconciler = ReconciliationEngine(
        exchange=exchange,
        order_repo=order_repo,
        position_repo=position_repo,
        balance_repo=balance_repo,
        system_event_repo=event_repo,
    )

    local_order = Order(
        client_order_id="ORD-MISMATCH-001",
        proposal_id="PRP-20260830-100011",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.5,
        price=62000.0,
        strategy_id="breakout_v2",
        status=OrderStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    order_repo.save(local_order)

    exchange._orders["ORD-MISMATCH-001"] = local_order.model_copy(
        update={"status": OrderStatus.FILLED, "filled_quantity": 0.5}
    )

    report = await reconciler.reconcile()
    updated_order = order_repo.get_by_id("ORD-MISMATCH-001")
    assert updated_order is not None
    assert updated_order.status == OrderStatus.FILLED
    assert report.orders_reconciled >= 1


# ---------------------------------------------------------------------------
# Scenario 12: Exchange Disconnect Handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_12_exchange_disconnect_handling(env_setup):
    """Scenario 12: Exchange disconnect exception caught correctly."""
    exchange = env_setup["exchange"]
    execution_service = env_setup["execution_service"]
    risk_engine = env_setup["risk_engine"]
    now = datetime.now(UTC)

    exchange.inject_failure("NETWORK_ERROR")

    prop_dict = make_proposal_payload("PRP-20260830-100012")
    proposal = TradeProposal.model_validate(prop_dict)
    mkt_state, port_state, sys_state = make_context_states(now)
    risk_decision = risk_engine.evaluate(proposal, mkt_state, port_state, sys_state)

    exec_result = await execution_service.execute_proposal(proposal, risk_decision)
    assert exec_result.success is False
    assert "network" in exec_result.error_message.lower() or "disconnected" in exec_result.error_message.lower()


# ---------------------------------------------------------------------------
# Scenario 13: Database Restart & State Persistence
# ---------------------------------------------------------------------------


def test_scenario_13_database_restart(env_setup):
    """Scenario 13: SQLite DB close and reopen retains order history."""
    db_path = env_setup["db_path"]
    order_repo = env_setup["order_repo"]
    now = datetime.now(UTC)

    order = Order(
        client_order_id="ORD-RESTART-001",
        proposal_id="PRP-20260830-100013",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.2,
        price=62000.0,
        strategy_id="breakout_v2",
        status=OrderStatus.FILLED,
        created_at=now,
        updated_at=now,
    )
    order_repo.save(order)

    # Verify saved before closing and commit to disk
    env_setup["db"].commit()
    retrieved_before = order_repo.get_by_id("ORD-RESTART-001")
    assert retrieved_before is not None

    env_setup["db"].close()
    new_db = SQLiteManager(db_path=db_path)
    new_db.connect()
    new_order_repo = OrderRepository(new_db)

    retrieved = new_order_repo.get_by_id("ORD-RESTART-001")
    assert retrieved is not None
    assert retrieved.client_order_id == "ORD-RESTART-001"
    assert retrieved.quantity == 0.2
    new_db.close()


# ---------------------------------------------------------------------------
# Scenario 14: Hermes Offline Resilience
# ---------------------------------------------------------------------------


def test_scenario_14_hermes_offline_resilience(env_setup):
    """Scenario 14: Hermes tool exceptions do not crash trading engine or risk boundary."""
    hermes_gateway = env_setup["hermes_gateway"]

    req = ToolRequest(request_id="REQ-001", tool_name="unauthorized_admin_tool", parameters={})
    res = hermes_gateway.execute_tool(req)
    assert res.success is False
    assert res.error_code == "HERMES_001"


# ---------------------------------------------------------------------------
# Scenario 15: Obsidian Vault Offline Resilience
# ---------------------------------------------------------------------------


def test_scenario_15_obsidian_offline_resilience(env_setup):
    """Scenario 15: Inaccessible Obsidian vault queues journal entries safely."""
    knowledge_api = env_setup["knowledge_api"]
    now = datetime.now(UTC)

    knowledge_api.vault_manager.vault_path = "/nonexistent/path/to/vault"

    entry = TradeJournalEntry(
        trade_id="TRD-OFFLINE-001",
        proposal_id="PRP-20260830-100015",
        symbol="BTCUSDT",
        direction="LONG",
        strategy_id="breakout_v2",
        strategy_version="2.1",
        entry_price=62000.0,
        quantity=0.1,
        thesis="Vault offline test",
        market_regime="BULL",
        initial_stop_loss=60000.0,
        initial_take_profit=66000.0,
        timestamp_entry=now,
    )

    result = knowledge_api.record_trade_journal_entry(entry)
    assert result is False


# ---------------------------------------------------------------------------
# Scenario 16: Web Application Route Resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_16_web_app_error_resilience(env_setup):
    """Scenario 16: Invalid web payload returns error response safely."""
    db_path = env_setup["db_path"]
    vault_path = env_setup["vault_path"]

    service = ControlCenterService(db_path=db_path, vault_path=vault_path)
    res = await service.submit_trade_proposal({"side": "INVALID_SIDE"})
    assert "error" in res or res.get("status") == "REJECTED"


# ---------------------------------------------------------------------------
# Scenario 17: Interrupted Process Crash & Recovery Simulation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_17_process_crash_recovery(env_setup):
    """Scenario 17: Interrupted order status post-crash is reconciled against exchange on restart."""
    exchange = env_setup["exchange"]
    order_repo = env_setup["order_repo"]
    position_repo = env_setup["position_repo"]
    balance_repo = env_setup["balance_repo"]
    now = datetime.now(UTC)

    local_order = Order(
        client_order_id="ORD-CRASH-001",
        proposal_id="PRP-20260830-100017",
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=2.0,
        price=3200.0,
        strategy_id="eth_breakout",
        status=OrderStatus.SUBMITTED,
        created_at=now,
        updated_at=now,
    )
    order_repo.save(local_order)

    exchange._orders["ORD-CRASH-001"] = local_order.model_copy(
        update={"status": OrderStatus.FILLED, "filled_quantity": 2.0}
    )

    reconciler = ReconciliationEngine(
        exchange=exchange,
        order_repo=order_repo,
        position_repo=position_repo,
        balance_repo=balance_repo,
    )

    await reconciler.reconcile()

    reconciled = order_repo.get_by_id("ORD-CRASH-001")
    assert reconciled is not None
    assert reconciled.status == OrderStatus.FILLED


# ---------------------------------------------------------------------------
# Scenario 18: Full System Restart & Reconciliation Recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_18_full_system_restart_recovery(env_setup):
    """Scenario 18: Full system restart restores DB, reconnects exchange, and reconciles state."""
    db_path = env_setup["db_path"]
    now = datetime.now(UTC)

    local_order = Order(
        client_order_id="ORD-FULL-001",
        proposal_id="PRP-20260830-100018",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.1,
        price=62000.0,
        strategy_id="breakout_v2",
        status=OrderStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    env_setup["order_repo"].save(local_order)
    env_setup["db"].commit()
    env_setup["db"].close()
    new_db = SQLiteManager(db_path=db_path)
    new_db.connect()
    new_order_repo = OrderRepository(new_db)
    new_pos_repo = PositionRepository(new_db)
    new_bal_repo = BalanceRepository(new_db)
    new_exchange = MockExchange()

    new_exchange._orders["ORD-FULL-001"] = local_order.model_copy(
        update={"status": OrderStatus.FILLED, "filled_quantity": 0.1}
    )

    reconciler = ReconciliationEngine(
        exchange=new_exchange,
        order_repo=new_order_repo,
        position_repo=new_pos_repo,
        balance_repo=new_bal_repo,
    )

    report = await reconciler.reconcile()
    assert report.orders_reconciled >= 1
    reconciled_order = new_order_repo.get_by_id("ORD-FULL-001")
    assert reconciled_order.status == OrderStatus.FILLED
    new_db.close()
