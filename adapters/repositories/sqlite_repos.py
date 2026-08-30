"""Repositories for SQLite operational state.

Provides type-safe CRUD operations, query methods, and domain model mapping
for all 10 canonical operational entities.
"""

from __future__ import annotations

import json
from typing import Any

from adapters.database.sqlite import SQLiteManager
from core.domain.enums import (
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
from core.errors import RecordNotFoundError

# ---------------------------------------------------------------------------
# TradeRepository
# ---------------------------------------------------------------------------


class TradeRepository:
    """Repository for managing trades table operations."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db

    def save(self, trade_data: dict[str, Any]) -> None:
        """Insert or update a trade record."""
        sql = """
            INSERT INTO trades (
                trade_id, proposal_id, symbol, side, strategy_id, strategy_version,
                model_version, risk_policy_version, entry_price, exit_price, quantity,
                gross_pnl, fees, slippage_cost, funding_cost, net_pnl, net_return,
                market_regime, llm_confidence, risk_decision, entry_at, exit_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                entry_price=excluded.entry_price,
                exit_price=excluded.exit_price,
                quantity=excluded.quantity,
                gross_pnl=excluded.gross_pnl,
                fees=excluded.fees,
                slippage_cost=excluded.slippage_cost,
                funding_cost=excluded.funding_cost,
                net_pnl=excluded.net_pnl,
                net_return=excluded.net_return,
                risk_decision=excluded.risk_decision,
                exit_at=excluded.exit_at,
                updated_at=excluded.updated_at
        """
        params = (
            trade_data["trade_id"],
            trade_data["proposal_id"],
            trade_data["symbol"],
            trade_data["side"],
            trade_data["strategy_id"],
            trade_data["strategy_version"],
            trade_data.get("model_version"),
            trade_data["risk_policy_version"],
            trade_data.get("entry_price"),
            trade_data.get("exit_price"),
            trade_data.get("quantity"),
            trade_data.get("gross_pnl"),
            trade_data.get("fees", 0.0),
            trade_data.get("slippage_cost", 0.0),
            trade_data.get("funding_cost", 0.0),
            trade_data.get("net_pnl"),
            trade_data.get("net_return"),
            trade_data.get("market_regime"),
            trade_data.get("llm_confidence"),
            trade_data["risk_decision"],
            trade_data.get("entry_at"),
            trade_data.get("exit_at"),
            trade_data["created_at"],
            trade_data["updated_at"],
        )
        self._db.execute(sql, params)

    def get_by_id(self, trade_id: str) -> dict[str, Any]:
        """Get trade by ID."""
        cursor = self._db.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
        row = cursor.fetchone()
        if not row:
            raise RecordNotFoundError(f"Trade not found: {trade_id}")
        return dict(row)

    def list_all(self) -> list[dict[str, Any]]:
        """List all trades."""
        cursor = self._db.execute("SELECT * FROM trades ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    get_all = list_all


# ---------------------------------------------------------------------------
# OrderRepository
# ---------------------------------------------------------------------------


class OrderRepository:
    """Repository for managing orders table operations."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db

    def save(self, order: Order) -> None:
        """Insert or update an Order domain model."""
        sql = """
            INSERT INTO orders (
                client_order_id, exchange_order_id, proposal_id, trade_id, symbol,
                side, order_type, quantity, filled_quantity, price, stop_price,
                average_fill_price, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_order_id) DO UPDATE SET
                exchange_order_id=excluded.exchange_order_id,
                trade_id=excluded.trade_id,
                filled_quantity=excluded.filled_quantity,
                average_fill_price=excluded.average_fill_price,
                status=excluded.status,
                updated_at=excluded.updated_at
        """
        params = (
            order.client_order_id,
            order.exchange_order_id,
            order.proposal_id,
            order.trade_id,
            order.symbol,
            order.side.value if isinstance(order.side, OrderSide) else order.side,
            order.order_type.value if isinstance(order.order_type, OrderType) else order.order_type,
            order.quantity,
            order.filled_quantity,
            order.price,
            order.stop_price,
            order.average_fill_price,
            order.status.value if isinstance(order.status, OrderStatus) else order.status,
            order.created_at.isoformat(),
            order.updated_at.isoformat(),
        )
        self._db.execute(sql, params)

    def get_by_id(self, client_order_id: str) -> Order:
        """Get Order by client_order_id."""
        cursor = self._db.execute(
            "SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise RecordNotFoundError(f"Order not found: {client_order_id}")
        return Order(
            client_order_id=row["client_order_id"],
            exchange_order_id=row["exchange_order_id"],
            proposal_id=row["proposal_id"],
            trade_id=row["trade_id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            order_type=OrderType(row["order_type"]),
            quantity=row["quantity"],
            filled_quantity=row["filled_quantity"],
            price=row["price"],
            stop_price=row["stop_price"],
            average_fill_price=row["average_fill_price"],
            status=OrderStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    save_order = save

    def update_order_status(
        self,
        client_order_id: str,
        status: OrderStatus | str,
        filled_quantity: float | None = None,
        average_fill_price: float | None = None,
    ) -> None:
        """Update status and fill details for an existing order."""
        status_str = status.value if isinstance(status, OrderStatus) else status
        if filled_quantity is not None and average_fill_price is not None:
            sql = """
                UPDATE orders SET status = ?, filled_quantity = ?, average_fill_price = ?,
                updated_at = datetime('now') WHERE client_order_id = ?
            """
            self._db.execute(
                sql, (status_str, filled_quantity, average_fill_price, client_order_id)
            )
        else:
            sql = """
                UPDATE orders SET status = ?, updated_at = datetime('now')
                WHERE client_order_id = ?
            """
            self._db.execute(sql, (status_str, client_order_id))

    def list_open_orders(self) -> list[Order]:
        """List active non-terminal orders."""
        cursor = self._db.execute(
            "SELECT * FROM orders WHERE status IN ('PENDING', 'SUBMITTED', 'PARTIAL') "
            "ORDER BY created_at ASC"
        )
        orders: list[Order] = []
        for row in cursor.fetchall():
            orders.append(
                Order(
                    client_order_id=row["client_order_id"],
                    exchange_order_id=row["exchange_order_id"],
                    proposal_id=row["proposal_id"],
                    trade_id=row["trade_id"],
                    symbol=row["symbol"],
                    side=OrderSide(row["side"]),
                    order_type=OrderType(row["order_type"]),
                    quantity=row["quantity"],
                    filled_quantity=row["filled_quantity"],
                    price=row["price"],
                    stop_price=row["stop_price"],
                    average_fill_price=row["average_fill_price"],
                    status=OrderStatus(row["status"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return orders

    get_open_orders = list_open_orders
    get_all = list_open_orders


# ---------------------------------------------------------------------------
# FillRepository
# ---------------------------------------------------------------------------


class FillRepository:
    """Repository for managing fills table operations."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db

    def save(self, fill: Fill) -> None:
        """Insert a Fill record."""
        sql = """
            INSERT INTO fills (
                fill_id, order_id, symbol, side, quantity, price, fee, fee_currency, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            fill.fill_id,
            fill.order_id,
            fill.symbol,
            fill.side.value if isinstance(fill.side, OrderSide) else fill.side,
            fill.quantity,
            fill.price,
            fill.fee,
            fill.fee_currency,
            fill.timestamp.isoformat(),
        )
        self._db.execute(sql, params)

    save_fill = save

    def get_by_id(self, fill_id: str) -> Fill:
        """Get Fill by fill_id."""
        cursor = self._db.execute("SELECT * FROM fills WHERE fill_id = ?", (fill_id,))
        row = cursor.fetchone()
        if not row:
            raise RecordNotFoundError(f"Fill not found: {fill_id}")
        return Fill(
            fill_id=row["fill_id"],
            order_id=row["order_id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            quantity=row["quantity"],
            price=row["price"],
            fee=row["fee"],
            fee_currency=row["fee_currency"],
            timestamp=row["timestamp"],
        )

    def get_by_order_id(self, order_id: str) -> list[Fill]:
        """Get all fills for a specific order."""
        cursor = self._db.execute(
            "SELECT * FROM fills WHERE order_id = ? ORDER BY timestamp ASC", (order_id,)
        )
        return [
            Fill(
                fill_id=row["fill_id"],
                order_id=row["order_id"],
                symbol=row["symbol"],
                side=OrderSide(row["side"]),
                quantity=row["quantity"],
                price=row["price"],
                fee=row["fee"],
                fee_currency=row["fee_currency"],
                timestamp=row["timestamp"],
            )
            for row in cursor.fetchall()
        ]


# ---------------------------------------------------------------------------
# PositionRepository
# ---------------------------------------------------------------------------


class PositionRepository:
    """Repository for managing positions table operations."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db

    def save(self, position: Position) -> None:
        """Insert or update a Position domain model."""
        sql = """
            INSERT INTO positions (
                position_id, symbol, side, quantity, entry_price, current_price,
                unrealized_pnl, realized_pnl, total_fees, total_funding, total_slippage,
                strategy_id, strategy_version, opened_at, closed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(position_id) DO UPDATE SET
                quantity=excluded.quantity,
                current_price=excluded.current_price,
                unrealized_pnl=excluded.unrealized_pnl,
                realized_pnl=excluded.realized_pnl,
                total_fees=excluded.total_fees,
                total_funding=excluded.total_funding,
                total_slippage=excluded.total_slippage,
                closed_at=excluded.closed_at,
                updated_at=excluded.updated_at
        """
        params = (
            position.position_id,
            position.symbol,
            position.side.value if isinstance(position.side, PositionSide) else position.side,
            position.quantity,
            position.entry_price,
            position.current_price,
            position.gross_pnl,
            position.realized_pnl,
            position.total_fees,
            position.total_funding,
            position.total_slippage,
            position.strategy_id,
            position.strategy_version,
            position.opened_at.isoformat(),
            position.closed_at.isoformat() if position.closed_at else None,
            position.updated_at.isoformat(),
        )
        self._db.execute(sql, params)

    save_position = save

    def get_by_id(self, position_id: str) -> Position:
        """Get Position by position_id."""
        cursor = self._db.execute("SELECT * FROM positions WHERE position_id = ?", (position_id,))
        row = cursor.fetchone()
        if not row:
            raise RecordNotFoundError(f"Position not found: {position_id}")
        return Position(
            position_id=row["position_id"],
            symbol=row["symbol"],
            side=PositionSide(row["side"]),
            quantity=row["quantity"],
            entry_price=row["entry_price"],
            current_price=row["current_price"],
            realized_pnl=row["realized_pnl"],
            total_fees=row["total_fees"],
            total_funding=row["total_funding"],
            total_slippage=row["total_slippage"],
            strategy_id=row["strategy_id"],
            strategy_version=row["strategy_version"],
            opened_at=row["opened_at"],
            closed_at=row["closed_at"],
            updated_at=row["updated_at"],
        )

    def list_open_positions(self) -> list[Position]:
        """List active open positions (closed_at IS NULL)."""
        cursor = self._db.execute(
            "SELECT * FROM positions WHERE closed_at IS NULL ORDER BY opened_at DESC"
        )
        positions: list[Position] = []
        for row in cursor.fetchall():
            positions.append(
                Position(
                    position_id=row["position_id"],
                    symbol=row["symbol"],
                    side=PositionSide(row["side"]),
                    quantity=row["quantity"],
                    entry_price=row["entry_price"],
                    current_price=row["current_price"],
                    realized_pnl=row["realized_pnl"],
                    total_fees=row["total_fees"],
                    total_funding=row["total_funding"],
                    total_slippage=row["total_slippage"],
                    strategy_id=row["strategy_id"],
                    strategy_version=row["strategy_version"],
                    opened_at=row["opened_at"],
                    closed_at=row["closed_at"],
                    updated_at=row["updated_at"],
                )
            )
        return positions

    get_open_positions = list_open_positions
    get_all = list_open_positions


# ---------------------------------------------------------------------------
# BalanceRepository
# ---------------------------------------------------------------------------


class BalanceRepository:
    """Repository for managing balances table operations."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db

    def save(
        self, currency: str, total: float, available: float, locked: float, source: str = "local"
    ) -> int:
        """Insert a new balance snapshot record."""
        sql = """
            INSERT INTO balances (currency, total, available, locked, source)
            VALUES (?, ?, ?, ?, ?)
        """
        cursor = self._db.execute(sql, (currency, total, available, locked, source))
        return cursor.lastrowid or 0

    def get_latest(self, currency: str, source: str = "local") -> dict[str, Any]:
        """Get latest balance record for currency and source."""
        cursor = self._db.execute(
            "SELECT * FROM balances WHERE currency = ? AND source = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (currency, source),
        )
        row = cursor.fetchone()
        if not row:
            raise RecordNotFoundError(f"Balance not found for {currency} ({source})")
        return dict(row)

    def get_all(self) -> list[dict[str, Any]]:
        """List all balances."""
        cursor = self._db.execute("SELECT * FROM balances ORDER BY timestamp DESC")
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# RiskDecisionRepository
# ---------------------------------------------------------------------------


class RiskDecisionRepository:
    """Repository for managing risk_decisions table operations."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db

    def save(self, decision: RiskDecision) -> None:
        """Insert or update a RiskDecision model."""
        sql = """
            INSERT INTO risk_decisions (
                decision_id, proposal_id, decision, violations,
                policy_version, computation_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(decision_id) DO UPDATE SET
                decision=excluded.decision,
                violations=excluded.violations
        """
        violations_json = (
            json.dumps([v.model_dump() for v in decision.violations])
            if decision.violations
            else None
        )
        params = (
            decision.decision_id,
            decision.proposal_id,
            decision.decision.value
            if isinstance(decision.decision, RiskDecisionType)
            else decision.decision,
            violations_json,
            decision.policy_version,
            decision.computation_ms,
            decision.timestamp.isoformat(),
        )
        self._db.execute(sql, params)

    def get_by_id(self, decision_id: str) -> RiskDecision:
        """Get RiskDecision by ID."""
        cursor = self._db.execute(
            "SELECT * FROM risk_decisions WHERE decision_id = ?", (decision_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise RecordNotFoundError(f"Risk decision not found: {decision_id}")

        violations = []
        if row["violations"]:
            v_list = json.loads(row["violations"])
            violations = [RiskViolation(**v) for v in v_list]

        return RiskDecision(
            decision_id=row["decision_id"],
            proposal_id=row["proposal_id"],
            decision=RiskDecisionType(row["decision"]),
            violations=violations,
            policy_version=row["policy_version"],
            computation_ms=row["computation_ms"],
            timestamp=row["created_at"],
        )

    def get_all(self) -> list[dict[str, Any]]:
        """List all risk decisions."""
        cursor = self._db.execute("SELECT * FROM risk_decisions ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# AuthorizationRepository
# ---------------------------------------------------------------------------


class AuthorizationRepository:
    """Repository for managing authorizations table operations."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db

    def save(self, proposal_id: str, decision_id: str, authorized_by: str, action: str) -> int:
        """Record an authorization record."""
        sql = """
            INSERT INTO authorizations (proposal_id, decision_id, authorized_by, action)
            VALUES (?, ?, ?, ?)
        """
        cursor = self._db.execute(sql, (proposal_id, decision_id, authorized_by, action))
        return cursor.lastrowid or 0

    record_authorization = save

    def get_by_proposal(self, proposal_id: str) -> list[dict[str, Any]]:
        """Get authorization audit records for a proposal."""
        cursor = self._db.execute(
            "SELECT * FROM authorizations WHERE proposal_id = ? ORDER BY created_at ASC",
            (proposal_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# StateTransitionRepository
# ---------------------------------------------------------------------------


class StateTransitionRepository:
    """Repository for managing state_transitions audit log operations."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db

    def save(
        self,
        entity_type: str,
        entity_id: str,
        from_state: ExecutionState | str,
        to_state: ExecutionState | str,
        reason: str | None = None,
    ) -> int:
        """Record a state transition in the audit log."""
        sql = """
            INSERT INTO state_transitions (entity_type, entity_id, from_state, to_state, reason)
            VALUES (?, ?, ?, ?, ?)
        """
        from_str = from_state.value if isinstance(from_state, ExecutionState) else from_state
        to_str = to_state.value if isinstance(to_state, ExecutionState) else to_state
        cursor = self._db.execute(sql, (entity_type, entity_id, from_str, to_str, reason))
        return cursor.lastrowid or 0

    record_transition = save

    def get_by_entity(self, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        """Get state transition history for an entity."""
        cursor = self._db.execute(
            "SELECT * FROM state_transitions WHERE entity_type = ? AND entity_id = ? "
            "ORDER BY created_at ASC",
            (entity_type, entity_id),
        )
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# SystemEventRepository
# ---------------------------------------------------------------------------


class SystemEventRepository:
    """Repository for managing system_events audit log operations."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db

    def save(self, event: AuditEvent) -> int:
        """Save an AuditEvent model to system_events."""
        sql = """
            INSERT INTO system_events (event_type, severity, source, message, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        metadata_json = json.dumps(event.metadata, default=str) if event.metadata else None
        params = (
            event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type),
            event.severity.value if hasattr(event.severity, "value") else str(event.severity),
            event.source,
            event.message,
            metadata_json,
            event.timestamp.isoformat(),
        )
        cursor = self._db.execute(sql, params)
        return cursor.lastrowid or 0

    def record_event(
        self,
        event_type: str,
        severity: str,
        source: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Record a system event by parameters."""
        sql = """
            INSERT INTO system_events (event_type, severity, source, message, metadata)
            VALUES (?, ?, ?, ?, ?)
        """
        meta_json = json.dumps(metadata, default=str) if metadata else None
        cursor = self._db.execute(sql, (event_type, severity, source, message, meta_json))
        return cursor.lastrowid or 0

    def get_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Get system events by event_type."""
        cursor = self._db.execute(
            "SELECT * FROM system_events WHERE event_type = ? ORDER BY created_at DESC",
            (event_type,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_by_source(self, source: str) -> list[dict[str, Any]]:
        """Get system events by source component."""
        cursor = self._db.execute(
            "SELECT * FROM system_events WHERE source = ? ORDER BY created_at DESC",
            (source,),
        )
        return [dict(row) for row in cursor.fetchall()]

    get_by_component = get_by_source

    def get_all(self, limit: int = 100) -> list[dict[str, Any]]:
        """List all system events."""
        cursor = self._db.execute(
            "SELECT * FROM system_events ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# StrategyVersionRepository
# ---------------------------------------------------------------------------


class StrategyVersionRepository:
    """Repository for managing strategy_versions table operations."""

    def __init__(self, db: SQLiteManager) -> None:
        self._db = db

    def save(self, strategy: StrategyVersion) -> None:
        """Insert or update StrategyVersion record."""
        sql = """
            INSERT INTO strategy_versions (strategy_id, version, config, lifecycle, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(strategy_id, version) DO UPDATE SET
                config=excluded.config,
                lifecycle=excluded.lifecycle
        """
        config_json = json.dumps(
            {
                "parameters": strategy.parameters,
                "risk_overrides": strategy.risk_overrides,
                "applicable_regimes": [r.value for r in strategy.applicable_regimes],
                "metadata": strategy.metadata,
            }
        )
        params = (
            strategy.strategy_id,
            strategy.version,
            config_json,
            strategy.lifecycle.value
            if isinstance(strategy.lifecycle, StrategyLifecycle)
            else strategy.lifecycle,
            strategy.created_at.isoformat(),
        )
        self._db.execute(sql, params)

    def get_version(self, strategy_id: str, version: str) -> StrategyVersion:
        """Get specific StrategyVersion record."""
        cursor = self._db.execute(
            "SELECT * FROM strategy_versions WHERE strategy_id = ? AND version = ?",
            (strategy_id, version),
        )
        row = cursor.fetchone()
        if not row:
            raise RecordNotFoundError(f"Strategy version not found: {strategy_id}:{version}")

        config = json.loads(row["config"])
        return StrategyVersion(
            strategy_id=row["strategy_id"],
            version=row["version"],
            lifecycle=StrategyLifecycle(row["lifecycle"]),
            parameters=config.get("parameters", {}),
            risk_overrides=config.get("risk_overrides", {}),
            applicable_regimes=config.get("applicable_regimes", []),
            metadata=config.get("metadata", {}),
            created_at=row["created_at"],
            created_by="system",
        )

    def get_all(self) -> list[dict[str, Any]]:
        """List all strategy versions."""
        cursor = self._db.execute("SELECT * FROM strategy_versions ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]
