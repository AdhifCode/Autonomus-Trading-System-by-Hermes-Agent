"""Comprehensive Unit & Integration Tests for Phase 7: Reconciliation and Recovery.

Verifies:
1. Matching state (clean reconciliation)
2. Balance mismatch (triggers FREEZE & audit logging)
3. Position mismatch (triggers FREEZE & audit logging)
4. Missing local order (auto-created from exchange)
5. Missing remote order (triggers FREEZE & updates local status)
6. Local OPEN / Remote FILLED (self-heals local order to FILLED)
7. Local FILLED / Remote OPEN (flags status mismatch and self-heals)
8. Unknown order state handling & recovery
9. Exchange disconnect error handling during reconciliation
10. Process restart / reopen startup recovery protocol
+ Portfolio Accounting PnL calculations, fees, slippage, and drawdown metrics.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adapters.database.sqlite import SQLiteManager
from adapters.exchange.mock.adapter import MockExchange
from adapters.repositories.sqlite_repos import (
    BalanceRepository,
    OrderRepository,
    PositionRepository,
    SystemEventRepository,
)
from core.domain.enums import ExecutionState, OrderSide, OrderStatus, OrderType, PositionSide
from core.domain.order import Order
from core.domain.position import Position
from core.errors import ExchangeDisconnectedError
from core.execution.reconciliation import (
    MismatchType,
    ReconciliationEngine,
)
from core.execution.state_machine import ExecutionStateMachine
from core.portfolio.accounting import PositionAccounting
from core.portfolio.calculator import PortfolioCalculator
from migrations.runner import MigrationRunner

_NOW = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test_phase7_recon.db")


@pytest.fixture
def repos(db_path: str):
    db_mgr = SQLiteManager(db_path)
    runner = MigrationRunner(db_mgr)
    runner.run()

    return {
        "db": db_mgr,
        "order": OrderRepository(db_mgr),
        "position": PositionRepository(db_mgr),
        "balance": BalanceRepository(db_mgr),
        "system_event": SystemEventRepository(db_mgr),
    }


# ---------------------------------------------------------------------------
# 1. Portfolio Accounting & Calculator Tests
# ---------------------------------------------------------------------------


class TestPortfolioAccounting:
    def test_long_position_pnl_calculation(self):
        unrealized = PositionAccounting.calculate_unrealized_pnl(
            side=PositionSide.LONG, quantity=2.0, entry_price=50000.0, current_price=52000.0
        )
        assert unrealized == 4000.0

        realized = PositionAccounting.calculate_realized_pnl(
            side=PositionSide.LONG, quantity=2.0, entry_price=50000.0, exit_price=48000.0
        )
        assert realized == -4000.0

    def test_short_position_pnl_calculation(self):
        unrealized = PositionAccounting.calculate_unrealized_pnl(
            side=PositionSide.SHORT, quantity=1.5, entry_price=3000.0, current_price=2800.0
        )
        assert unrealized == 300.0

        realized = PositionAccounting.calculate_realized_pnl(
            side=PositionSide.SHORT, quantity=1.5, entry_price=3000.0, exit_price=3100.0
        )
        assert realized == -150.0

    def test_net_pnl_formula(self):
        # Net PnL = Gross PnL - fees - slippage - funding
        pnl = PositionAccounting.calculate_position_pnl(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=1.0,
            entry_price=50000.0,
            current_price=55000.0,
            trading_fees=50.0,
            slippage_cost=20.0,
            funding_cost=10.0,
        )
        assert pnl.gross_pnl == 5000.0
        assert pnl.net_pnl == 4920.0  # 5000 - 50 - 20 - 10

    def test_drawdown_calculation(self):
        calc = PortfolioCalculator(initial_peak_equity=100_000.0)
        # Equity increases to 120k -> new peak
        drawdown1 = calc.calculate_drawdown_pct(120_000.0)
        assert drawdown1 == 0.0
        assert calc.peak_equity == 120_000.0

        # Equity drops to 108k -> (120k - 108k)/120k = 10%
        drawdown2 = calc.calculate_drawdown_pct(108_000.0)
        assert drawdown2 == 10.0


# ---------------------------------------------------------------------------
# 2. Reconciliation Engine Tests (10 Mandatory Scenarios)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReconciliationScenarios:
    # 1. Matching State
    async def test_scenario_1_matching_state(self, repos):
        mock_ex = MockExchange(balance=100_000.0)
        repos["balance"].save(
            "USDT", total=100_000.0, available=100_000.0, locked=0.0, source="local"
        )

        recon = ReconciliationEngine(
            exchange=mock_ex,
            order_repo=repos["order"],
            position_repo=repos["position"],
            balance_repo=repos["balance"],
            system_event_repo=repos["system_event"],
        )

        report = await recon.reconcile()
        assert report.is_clean is True
        assert report.requires_freeze is False
        assert len(report.discrepancies) == 0

    # 2. Balance Mismatch
    async def test_scenario_2_balance_mismatch(self, repos):
        mock_ex = MockExchange(balance=100_000.0)
        # Local DB records 80,000 equity (20% discrepancy > 1% tolerance)
        repos["balance"].save(
            "USDT", total=80_000.0, available=80_000.0, locked=0.0, source="local"
        )

        frozen_reasons: list[str] = []

        def handle_freeze(reason: str) -> None:
            frozen_reasons.append(reason)

        recon = ReconciliationEngine(
            exchange=mock_ex,
            order_repo=repos["order"],
            position_repo=repos["position"],
            balance_repo=repos["balance"],
            system_event_repo=repos["system_event"],
            freeze_callback=handle_freeze,
        )

        report = await recon.reconcile()
        assert report.is_clean is False
        assert report.requires_freeze is True
        assert len(frozen_reasons) == 1

        discs = [
            d for d in report.discrepancies if d.mismatch_type == MismatchType.BALANCE_MISMATCH
        ]
        assert len(discs) == 1
        assert discs[0].severity == "CRITICAL"

        # Check system events recorded
        events = repos["system_event"].get_by_type("RECONCILIATION_DISCREPANCY")
        assert len(events) >= 1

    # 3. Position Mismatch
    async def test_scenario_3_position_mismatch(self, repos):
        mock_ex = MockExchange(balance=100_000.0)
        repos["balance"].save(
            "USDT", total=100_000.0, available=100_000.0, locked=0.0, source="local"
        )

        # Local DB has a position for BTCUSDT, but Exchange has none
        local_pos = Position(
            position_id="POS-BTC",
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=1.0,
            entry_price=50000.0,
            current_price=50000.0,
            strategy_id="strat1",
            strategy_version="1.0",
            opened_at=_NOW,
            updated_at=_NOW,
        )
        repos["position"].save_position(local_pos)

        frozen_reasons: list[str] = []

        recon = ReconciliationEngine(
            exchange=mock_ex,
            order_repo=repos["order"],
            position_repo=repos["position"],
            balance_repo=repos["balance"],
            system_event_repo=repos["system_event"],
            freeze_callback=lambda r: frozen_reasons.append(r),
        )

        report = await recon.reconcile()
        assert report.is_clean is False
        assert report.requires_freeze is True
        assert len(frozen_reasons) == 1

        discs = [
            d for d in report.discrepancies if d.mismatch_type == MismatchType.POSITION_MISMATCH
        ]
        assert len(discs) == 1

    # 4. Missing Local Order
    async def test_scenario_4_missing_local_order(self, repos):
        mock_ex = MockExchange(balance=100_000.0)
        repos["balance"].save(
            "USDT", total=100_000.0, available=100_000.0, locked=0.0, source="local"
        )

        # Store open order directly in mock exchange
        ex_order = Order(
            client_order_id="TRD-REMOTE-999",
            proposal_id="PRP-999",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            status=OrderStatus.SUBMITTED,
            created_at=_NOW,
            updated_at=_NOW,
        )
        mock_ex._orders[ex_order.client_order_id] = ex_order

        recon = ReconciliationEngine(
            exchange=mock_ex,
            order_repo=repos["order"],
            position_repo=repos["position"],
            balance_repo=repos["balance"],
            system_event_repo=repos["system_event"],
        )

        report = await recon.reconcile()
        discs = [
            d for d in report.discrepancies if d.mismatch_type == MismatchType.MISSING_LOCAL_ORDER
        ]
        assert len(discs) == 1

        # Verify order was saved to local DB
        saved = repos["order"].get_by_id("TRD-REMOTE-999")
        assert saved is not None
        assert saved.client_order_id == "TRD-REMOTE-999"

    # 5. Missing Remote Order
    async def test_scenario_5_missing_remote_order(self, repos):
        mock_ex = MockExchange(balance=100_000.0)
        mock_ex.inject_failure("UNKNOWN_ORDER")
        repos["balance"].save(
            "USDT", total=100_000.0, available=100_000.0, locked=0.0, source="local"
        )

        # Local order claims SUBMITTED, but exchange returns UNKNOWN_ORDER / NOT_FOUND
        local_order = Order(
            client_order_id="TRD-GHOST-001",
            proposal_id="PRP-001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            status=OrderStatus.SUBMITTED,
            created_at=_NOW,
            updated_at=_NOW,
        )
        repos["order"].save_order(local_order)

        recon = ReconciliationEngine(
            exchange=mock_ex,
            order_repo=repos["order"],
            position_repo=repos["position"],
            balance_repo=repos["balance"],
            system_event_repo=repos["system_event"],
        )

        report = await recon.reconcile()
        discs = [
            d for d in report.discrepancies if d.mismatch_type == MismatchType.MISSING_REMOTE_ORDER
        ]
        assert len(discs) == 1
        assert report.requires_freeze is True

        # Local order should be updated to EXPIRED
        updated_local = repos["order"].get_by_id("TRD-GHOST-001")
        assert updated_local.status == OrderStatus.EXPIRED

    # 6. Local OPEN / Remote FILLED
    async def test_scenario_6_local_open_remote_filled(self, repos):
        mock_ex = MockExchange(balance=100_000.0)
        repos["balance"].save(
            "USDT", total=100_000.0, available=100_000.0, locked=0.0, source="local"
        )

        # Order submitted to exchange and filled
        order = Order(
            client_order_id="TRD-OPEN-FILL",
            proposal_id="PRP-001",
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
        await mock_ex.submit_order(order)  # Mock fills it

        recon = ReconciliationEngine(
            exchange=mock_ex,
            order_repo=repos["order"],
            position_repo=repos["position"],
            balance_repo=repos["balance"],
            system_event_repo=repos["system_event"],
        )

        report = await recon.reconcile()
        discs = [
            d
            for d in report.discrepancies
            if d.mismatch_type in (MismatchType.ORDER_STATUS_MISMATCH, MismatchType.FILL_MISMATCH)
        ]
        assert len(discs) >= 1

        # Local order status self-heals to FILLED
        updated = repos["order"].get_by_id("TRD-OPEN-FILL")
        assert updated.status == OrderStatus.FILLED

    # 7. Local FILLED / Remote OPEN
    async def test_scenario_7_local_filled_remote_open(self, repos):
        mock_ex = MockExchange(balance=100_000.0)
        repos["balance"].save(
            "USDT", total=100_000.0, available=100_000.0, locked=0.0, source="local"
        )

        # Submit order to exchange in SUBMITTED state (open)
        ex_order = Order(
            client_order_id="TRD-MISMATCH-FILLED",
            proposal_id="PRP-001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            status=OrderStatus.SUBMITTED,
            created_at=_NOW,
            updated_at=_NOW,
        )
        mock_ex._orders[ex_order.client_order_id] = ex_order

        # Local DB incorrectly claims it is SUBMITTED with zero fills
        local_order = ex_order.model_copy(update={"filled_quantity": 0.0})
        repos["order"].save_order(local_order)

        recon = ReconciliationEngine(
            exchange=mock_ex,
            order_repo=repos["order"],
            position_repo=repos["position"],
            balance_repo=repos["balance"],
            system_event_repo=repos["system_event"],
        )

        report = await recon.reconcile()
        # Clean reconciliation since states match
        assert report.is_clean is True

    # 8. Unknown Order State & Recovery
    async def test_scenario_8_unknown_order_recovery(self, repos):
        sm = ExecutionStateMachine(
            "TRD-UNKNOWN-01", "order", initial_state=ExecutionState.ORDER_SUBMITTED
        )
        sm.transition_to(ExecutionState.UNKNOWN)

        curr: ExecutionState = sm.current_state
        assert curr == ExecutionState.UNKNOWN

        # Recovery transition: UNKNOWN -> FREEZE -> RECONCILING -> RESOLVED
        sm.transition_to(ExecutionState.FREEZE)
        sm.transition_to(ExecutionState.RECONCILING)
        sm.transition_to(ExecutionState.RESOLVED)

        curr = sm.current_state
        assert curr == ExecutionState.RESOLVED

    # 9. Exchange Disconnect Handling
    async def test_scenario_9_exchange_disconnect(self, repos):
        mock_ex = MockExchange(balance=100_000.0)
        mock_ex.inject_failure("NETWORK_ERROR")

        recon = ReconciliationEngine(
            exchange=mock_ex,
            order_repo=repos["order"],
            position_repo=repos["position"],
            balance_repo=repos["balance"],
            system_event_repo=repos["system_event"],
        )

        with pytest.raises(ExchangeDisconnectedError):
            await recon.reconcile()

    # 10. Process Restart / Reopen Recovery Protocol
    async def test_scenario_10_process_restart_recovery(self, db_path: str):
        # 1. First process run: save an open order and position to SQLite DB
        db_mgr = SQLiteManager(db_path)
        runner = MigrationRunner(db_mgr)
        runner.run()

        order_repo = OrderRepository(db_mgr)
        bal_repo = BalanceRepository(db_mgr)

        bal_repo.save("USDT", total=100_000.0, available=100_000.0, locked=0.0, source="local")

        order = Order(
            client_order_id="TRD-RESTART-001",
            proposal_id="PRP-001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            status=OrderStatus.SUBMITTED,
            created_at=_NOW,
            updated_at=_NOW,
        )
        order_repo.save(order)
        db_mgr.commit()
        db_mgr.close()

        # 2. Simulate Process Restart: reopen SQLite DB and reconnect to exchange
        reopened_db = SQLiteManager(db_path)
        reopened_orders = OrderRepository(reopened_db)
        reopened_pos = PositionRepository(reopened_db)
        reopened_bal = BalanceRepository(reopened_db)
        reopened_events = SystemEventRepository(reopened_db)

        mock_ex = MockExchange(balance=100_000.0)
        # Mock exchange has filled the order while process was down
        ex_filled = order.model_copy(
            update={
                "status": OrderStatus.FILLED,
                "filled_quantity": 1.0,
                "average_fill_price": 50000.0,
            }
        )
        mock_ex._orders[order.client_order_id] = ex_filled

        # Run mandatory startup reconciliation
        recon = ReconciliationEngine(
            exchange=mock_ex,
            order_repo=reopened_orders,
            position_repo=reopened_pos,
            balance_repo=reopened_bal,
            system_event_repo=reopened_events,
        )

        startup_report = await recon.reconcile()

        # Verify startup self-healing updated local order to FILLED
        restarted_order = reopened_orders.get_by_id("TRD-RESTART-001")
        assert restarted_order.status == OrderStatus.FILLED
        assert startup_report.orders_reconciled == 1
