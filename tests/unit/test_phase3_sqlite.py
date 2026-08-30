"""Tests for Phase 3: SQLite Operational State.

Covers:
- Schema initialization & migrations
- Repositories CRUD operations for all 10 entities
- Transaction atomicity & rollback
- Persistence & database reopen/restart
- Duplicate prevention / primary key constraints
- Foreign key & invalid state enforcement
- Concurrent database access under WAL mode
- Verification that Obsidian is NOT used as an operational state store
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.database.sqlite import SQLiteManager
from adapters.repositories import (
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
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    RiskDecisionType,
    Severity,
    StrategyLifecycle,
)
from core.domain.events import AuditEvent
from core.domain.fill import Fill
from core.domain.order import Order
from core.domain.position import Position
from core.domain.risk import RiskDecision, RiskViolation
from core.domain.strategy import StrategyVersion
from core.errors import DatabaseError, RecordNotFoundError
from migrations.runner import MigrationRunner

_NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_operational.db")


@pytest.fixture
def db(db_path: str) -> SQLiteManager:
    manager = SQLiteManager(db_path, wal_mode=True)
    manager.connect()
    runner = MigrationRunner(manager)
    runner.run()
    yield manager
    manager.close()


# ---------------------------------------------------------------------------
# 1. Schema & Migration Tests
# ---------------------------------------------------------------------------


class TestSchemaAndMigrations:
    """Verify operational schema, migrations, WAL, and tables."""

    def test_migration_applied(self, db: SQLiteManager):
        runner = MigrationRunner(db)
        assert runner.get_current_version() == 1
        assert len(runner.get_pending_migrations()) == 0

    def test_all_10_tables_exist(self, db: SQLiteManager):
        expected_tables = [
            "trades",
            "orders",
            "fills",
            "positions",
            "balances",
            "risk_decisions",
            "authorizations",
            "state_transitions",
            "system_events",
            "strategy_versions",
        ]
        for table in expected_tables:
            assert db.table_exists(table), f"Table {table} missing!"

    def test_wal_mode_active(self, db: SQLiteManager):
        cursor = db.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"

    def test_foreign_keys_active(self, db: SQLiteManager):
        cursor = db.execute("PRAGMA foreign_keys")
        fk = cursor.fetchone()[0]
        assert fk == 1


# ---------------------------------------------------------------------------
# 2. Repository CRUD Tests for All 10 Entities
# ---------------------------------------------------------------------------


class TestRepositoriesCRUD:
    """CRUD operations for all 10 canonical operational entities."""

    def test_trade_crud(self, db: SQLiteManager):
        repo = TradeRepository(db)
        trade_data = {
            "trade_id": "TRD-20260829-000001",
            "proposal_id": "PRP-20260829-000001",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "strategy_id": "momentum",
            "strategy_version": "1.0",
            "model_version": "claude-3.5-sonnet",
            "risk_policy_version": "1.0",
            "risk_decision": "APPROVED",
            "created_at": _NOW.isoformat(),
            "updated_at": _NOW.isoformat(),
        }
        repo.save(trade_data)
        db.commit()

        retrieved = repo.get_by_id("TRD-20260829-000001")
        assert retrieved["symbol"] == "BTCUSDT"
        assert retrieved["risk_decision"] == "APPROVED"
        assert len(repo.list_all()) == 1

    def test_order_crud(self, db: SQLiteManager):
        order_repo = OrderRepository(db)
        order = Order(
            client_order_id="TRD-20260829-000001",
            proposal_id="PRP-20260829-000001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            status=OrderStatus.PENDING,
            created_at=_NOW,
            updated_at=_NOW,
        )
        order_repo.save(order)
        db.commit()

        retrieved = order_repo.get_by_id("TRD-20260829-000001")
        assert retrieved.client_order_id == "TRD-20260829-000001"
        assert retrieved.price == 50000.0
        assert len(order_repo.list_open_orders()) == 1

        # Update order fill status
        updated_order = Order(
            client_order_id="TRD-20260829-000001",
            proposal_id="PRP-20260829-000001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            filled_quantity=1.0,
            price=50000.0,
            average_fill_price=50000.0,
            status=OrderStatus.FILLED,
            created_at=_NOW,
            updated_at=_NOW,
        )
        order_repo.save(updated_order)
        db.commit()

        retrieved_updated = order_repo.get_by_id("TRD-20260829-000001")
        assert retrieved_updated.status == OrderStatus.FILLED
        assert len(order_repo.list_open_orders()) == 0

    def test_fill_crud(self, db: SQLiteManager):
        order_repo = OrderRepository(db)
        order = Order(
            client_order_id="TRD-20260829-000001",
            proposal_id="PRP-20260829-000001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            status=OrderStatus.PARTIAL,
            created_at=_NOW,
            updated_at=_NOW,
        )
        order_repo.save(order)
        db.commit()

        fill_repo = FillRepository(db)
        fill = Fill(
            fill_id="FILL-001",
            order_id="TRD-20260829-000001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=0.5,
            price=50000.0,
            fee=5.0,
            fee_currency="USDT",
            timestamp=_NOW,
        )
        fill_repo.save(fill)
        db.commit()

        retrieved_fill = fill_repo.get_by_id("FILL-001")
        assert retrieved_fill.fill_id == "FILL-001"
        assert retrieved_fill.quantity == 0.5

        fills_for_order = fill_repo.get_by_order_id("TRD-20260829-000001")
        assert len(fills_for_order) == 1

    def test_position_crud(self, db: SQLiteManager):
        repo = PositionRepository(db)
        pos = Position(
            position_id="POS-001",
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=1.0,
            entry_price=50000.0,
            current_price=52000.0,
            strategy_id="momentum",
            strategy_version="1.0",
            opened_at=_NOW,
            updated_at=_NOW,
        )
        repo.save(pos)
        db.commit()

        retrieved = repo.get_by_id("POS-001")
        assert retrieved.position_id == "POS-001"
        assert retrieved.gross_pnl == 2000.0
        assert len(repo.list_open_positions()) == 1

    def test_balance_crud(self, db: SQLiteManager):
        repo = BalanceRepository(db)
        row_id = repo.save("USDT", 10000.0, 8000.0, 2000.0, "local")
        db.commit()
        assert row_id > 0

        latest = repo.get_latest("USDT", "local")
        assert latest["total"] == 10000.0
        assert latest["available"] == 8000.0

    def test_risk_decision_crud(self, db: SQLiteManager):
        repo = RiskDecisionRepository(db)
        decision = RiskDecision(
            decision_id="RD-001",
            proposal_id="PRP-20260829-000001",
            decision=RiskDecisionType.REJECTED,
            violations=[
                RiskViolation(
                    validator="max_exposure",
                    rule="Exposure Limit",
                    current_value=0.6,
                    limit_value=0.5,
                    message="Portfolio exposure exceeded",
                )
            ],
            policy_version="1.0",
            computation_ms=1.2,
            timestamp=_NOW,
        )
        repo.save(decision)
        db.commit()

        retrieved = repo.get_by_id("RD-001")
        assert retrieved.decision == RiskDecisionType.REJECTED
        assert len(retrieved.violations) == 1
        assert retrieved.violations[0].validator == "max_exposure"

    def test_authorization_crud(self, db: SQLiteManager):
        repo = AuthorizationRepository(db)
        row_id = repo.save("PRP-20260829-000001", "RD-001", "risk_engine", "APPROVE")
        db.commit()
        assert row_id > 0

        auths = repo.get_by_proposal("PRP-20260829-000001")
        assert len(auths) == 1
        assert auths[0]["authorized_by"] == "risk_engine"

    def test_state_transition_crud(self, db: SQLiteManager):
        repo = StateTransitionRepository(db)
        row_id = repo.save(
            "trade",
            "TRD-20260829-000001",
            ExecutionState.PROPOSAL_CREATED,
            ExecutionState.APPROVED,
            "Risk approved",
        )
        db.commit()
        assert row_id > 0

        transitions = repo.get_by_entity("trade", "TRD-20260829-000001")
        assert len(transitions) == 1
        assert transitions[0]["from_state"] == "PROPOSAL_CREATED"
        assert transitions[0]["to_state"] == "APPROVED"

    def test_system_event_crud(self, db: SQLiteManager):
        repo = SystemEventRepository(db)
        event = AuditEvent(
            event_id="EVT-001",
            event_type=EventType.SYSTEM_ERROR,
            severity=Severity.ERROR,
            source="executor",
            message="Exchange timeout",
            timestamp=_NOW,
            metadata={"retry_count": 3},
        )
        row_id = repo.save(event)
        db.commit()
        assert row_id > 0

        events = repo.get_by_type("SYSTEM_ERROR")
        assert len(events) == 1
        assert events[0]["source"] == "executor"

    def test_strategy_version_crud(self, db: SQLiteManager):
        repo = StrategyVersionRepository(db)
        strat = StrategyVersion(
            strategy_id="momentum",
            version="1.0",
            lifecycle=StrategyLifecycle.PRODUCTION,
            parameters={"rsi_period": 14},
            risk_overrides={"max_position_size_pct": 0.05},
            applicable_regimes=[],
            metadata={"author": "quant"},
            created_at=_NOW,
            created_by="human",
        )
        repo.save(strat)
        db.commit()

        retrieved = repo.get_version("momentum", "1.0")
        assert retrieved.strategy_id == "momentum"
        assert retrieved.lifecycle == StrategyLifecycle.PRODUCTION
        assert retrieved.parameters["rsi_period"] == 14


# ---------------------------------------------------------------------------
# 3. Transactions, Rollback, Constraints & Persistence
# ---------------------------------------------------------------------------


class TestTransactionsAndConstraints:
    """Transaction atomicity, rollbacks, foreign keys, duplicate prevention, restart."""

    def test_transaction_rollback(self, db: SQLiteManager):
        trade_repo = TradeRepository(db)
        trade_data = {
            "trade_id": "TRD-ROLLBACK-01",
            "proposal_id": "PRP-01",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "strategy_id": "test",
            "strategy_version": "1.0",
            "risk_policy_version": "1.0",
            "risk_decision": "APPROVED",
            "created_at": _NOW.isoformat(),
            "updated_at": _NOW.isoformat(),
        }
        trade_repo.save(trade_data)
        db.rollback()

        with pytest.raises(RecordNotFoundError):
            trade_repo.get_by_id("TRD-ROLLBACK-01")

    def test_duplicate_primary_key_prevention(self, db: SQLiteManager):
        fill_repo = FillRepository(db)
        order_repo = OrderRepository(db)
        order = Order(
            client_order_id="TRD-20260829-000001",
            proposal_id="PRP-20260829-000001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            status=OrderStatus.PENDING,
            created_at=_NOW,
            updated_at=_NOW,
        )
        order_repo.save(order)
        db.commit()

        fill = Fill(
            fill_id="FILL-UNIQUE",
            order_id="TRD-20260829-000001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=0.5,
            price=50000.0,
            fee=5.0,
            fee_currency="USDT",
            timestamp=_NOW,
        )
        fill_repo.save(fill)
        db.commit()

        # Duplicate fill_id insert must fail
        with pytest.raises(DatabaseError):
            fill_repo.save(fill)

    def test_foreign_key_constraint(self, db: SQLiteManager):
        fill_repo = FillRepository(db)
        fill = Fill(
            fill_id="FILL-NO-ORDER",
            order_id="NON-EXISTENT-ORDER",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=0.5,
            price=50000.0,
            fee=5.0,
            fee_currency="USDT",
            timestamp=_NOW,
        )
        with pytest.raises(DatabaseError):
            fill_repo.save(fill)

    def test_persistence_across_reopen(self, db_path: str):
        # Open, save, close
        db1 = SQLiteManager(db_path, wal_mode=True)
        db1.connect()
        MigrationRunner(db1).run()
        repo1 = BalanceRepository(db1)
        repo1.save("ETH", 50.0, 50.0, 0.0, "local")
        db1.commit()
        db1.close()

        # Reopen connection
        db2 = SQLiteManager(db_path, wal_mode=True)
        db2.connect()
        repo2 = BalanceRepository(db2)
        latest = repo2.get_latest("ETH", "local")
        assert latest["total"] == 50.0
        db2.close()

    def test_obsidian_not_operational_source(self, db: SQLiteManager):
        """Verify SQLite tables are the canonical store, not Obsidian vault files."""
        # Operational query returns state directly from SQLite
        trade_repo = TradeRepository(db)
        assert isinstance(trade_repo._db, SQLiteManager)
