"""Reconciliation Engine Module.

Compairs local operational state (orders, positions, balances in SQLite) against exchange truth,
detects discrepancies across 7 mismatch classifications, updates order status, logs audit events,
and triggers system FREEZE on critical financial mismatches.

Rule: Never guess. Authoritative exchange state is canonical.
See architecture §17 and implementation_spec §9.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, Field

from adapters.exchange.base import ExchangeAdapter
from adapters.repositories.sqlite_repos import (
    BalanceRepository,
    OrderRepository,
    PositionRepository,
    SystemEventRepository,
)
from core.domain.enums import OrderStatus
from core.domain.order import Order
from core.domain.position import Position
from core.errors import ExchangeDisconnectedError, RecordNotFoundError
from core.logging import get_logger

logger = get_logger(__name__)


class MismatchType(StrEnum):
    """Classification of state discrepancies detected during reconciliation."""

    MATCH = "MATCH"
    ORDER_STATUS_MISMATCH = "ORDER_STATUS_MISMATCH"
    MISSING_LOCAL_ORDER = "MISSING_LOCAL_ORDER"
    MISSING_REMOTE_ORDER = "MISSING_REMOTE_ORDER"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    BALANCE_MISMATCH = "BALANCE_MISMATCH"
    FILL_MISMATCH = "FILL_MISMATCH"


class Discrepancy(BaseModel):
    """Details of a state discrepancy detected between local DB and exchange."""

    entity_type: str = Field(min_length=1)  # 'order', 'position', 'balance'
    entity_id: str = Field(min_length=1)
    mismatch_type: MismatchType
    severity: str = Field(min_length=1)  # 'WARNING', 'CRITICAL'
    local_state: str = Field(min_length=1)
    exchange_state: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ReconciliationReport(BaseModel):
    """Structured report produced by reconciliation algorithm."""

    is_clean: bool
    requires_freeze: bool = False
    discrepancies: list[Discrepancy]
    orders_reconciled: int
    positions_reconciled: int
    timestamp_str: str


class ReconciliationEngine:
    """Reconciles local SQLite operational state against authoritative exchange state."""

    def __init__(
        self,
        exchange: ExchangeAdapter,
        order_repo: OrderRepository,
        position_repo: PositionRepository,
        balance_repo: BalanceRepository,
        system_event_repo: SystemEventRepository | None = None,
        balance_tolerance_pct: float = 0.01,
        freeze_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.exchange = exchange
        self.order_repo = order_repo
        self.position_repo = position_repo
        self.balance_repo = balance_repo
        self.system_event_repo = system_event_repo
        self.balance_tolerance_pct = balance_tolerance_pct
        self.freeze_callback = freeze_callback

    async def reconcile(self) -> ReconciliationReport:
        """Run full reconciliation across balances, positions, and open orders.

        Rule: Never guess.
        - Self-heals local order status for soft mismatches.
        - Creates missing local orders found on exchange.
        - Triggers system FREEZE and records CRITICAL audit events for position/balance mismatches.
        """
        discrepancies: list[Discrepancy] = []
        requires_freeze = False

        # 1. Fetch Exchange Authoritative State
        try:
            ex_account = await self.exchange.get_account()
            ex_orders = await self.exchange.get_open_orders()
            ex_positions = await self.exchange.get_positions()
        except ExchangeDisconnectedError as e:
            logger.error("Reconciliation aborted: Exchange disconnected: %s", e)
            raise

        # 2. Fetch Local SQLite Operational State
        local_orders = self.order_repo.get_open_orders()
        local_positions = self.position_repo.get_open_positions()

        # 3. Reconcile Balances
        ex_equity = ex_account.get("equity", 0.0)
        try:
            local_bal_record = self.balance_repo.get_latest("USDT", source="local")
            loc_equity = local_bal_record.get("total", 0.0)
            if ex_equity > 0:
                diff_pct = abs(loc_equity - ex_equity) / ex_equity
                if diff_pct > self.balance_tolerance_pct:
                    disc = Discrepancy(
                        entity_type="balance",
                        entity_id="wallet",
                        mismatch_type=MismatchType.BALANCE_MISMATCH,
                        severity="CRITICAL",
                        local_state=f"equity={loc_equity}",
                        exchange_state=f"equity={ex_equity}",
                        message=(
                            f"Balance discrepancy of {diff_pct * 100:.2f}% "
                            f"exceeds tolerance ({self.balance_tolerance_pct * 100}%)"
                        ),
                    )
                    discrepancies.append(disc)
                    requires_freeze = True
        except RecordNotFoundError:
            logger.debug("No local balance record found for reconciliation.")

        # 4. Reconcile Orders
        ex_order_map: dict[str, Order] = {o.client_order_id: o for o in ex_orders}
        processed_ex_cids: set[str] = set()

        for local_ord in local_orders:
            cid = local_ord.client_order_id
            if cid in ex_order_map:
                processed_ex_cids.add(cid)
                ex_ord = ex_order_map[cid]

                if local_ord.filled_quantity != ex_ord.filled_quantity:
                    disc = Discrepancy(
                        entity_type="order",
                        entity_id=cid,
                        mismatch_type=MismatchType.FILL_MISMATCH,
                        severity="WARNING",
                        local_state=f"filled: {local_ord.filled_quantity}",
                        exchange_state=f"filled: {ex_ord.filled_quantity}",
                        message=f"Fill quantity mismatch for order {cid}",
                    )
                    discrepancies.append(disc)
                    self.order_repo.update_order_status(
                        client_order_id=cid,
                        status=ex_ord.status,
                        filled_quantity=ex_ord.filled_quantity,
                        average_fill_price=ex_ord.average_fill_price,
                    )
                elif local_ord.status != ex_ord.status:
                    disc = Discrepancy(
                        entity_type="order",
                        entity_id=cid,
                        mismatch_type=MismatchType.ORDER_STATUS_MISMATCH,
                        severity="WARNING",
                        local_state=local_ord.status.value,
                        exchange_state=ex_ord.status.value,
                        message=(
                            f"Order status mismatch for {cid}: "
                            f"local={local_ord.status.value}, ex={ex_ord.status.value}"
                        ),
                    )
                    discrepancies.append(disc)
                    self.order_repo.update_order_status(
                        client_order_id=cid,
                        status=ex_ord.status,
                        filled_quantity=ex_ord.filled_quantity,
                        average_fill_price=ex_ord.average_fill_price,
                    )
            else:
                # Local order claims open, but not in exchange open_orders list
                try:
                    ex_ord = await self.exchange.get_order(cid)
                    if (
                        local_ord.status != ex_ord.status
                        or local_ord.filled_quantity != ex_ord.filled_quantity
                    ):
                        m_type = (
                            MismatchType.FILL_MISMATCH
                            if local_ord.filled_quantity != ex_ord.filled_quantity
                            else MismatchType.ORDER_STATUS_MISMATCH
                        )
                        disc = Discrepancy(
                            entity_type="order",
                            entity_id=cid,
                            mismatch_type=m_type,
                            severity="WARNING",
                            local_state=f"{local_ord.status.value}:{local_ord.filled_quantity}",
                            exchange_state=f"{ex_ord.status.value}:{ex_ord.filled_quantity}",
                            message=f"Local order {cid} self-healed to {ex_ord.status.value}",
                        )
                        discrepancies.append(disc)
                        self.order_repo.update_order_status(
                            client_order_id=cid,
                            status=ex_ord.status,
                            filled_quantity=ex_ord.filled_quantity,
                            average_fill_price=ex_ord.average_fill_price,
                        )
                except RecordNotFoundError:
                    disc = Discrepancy(
                        entity_type="order",
                        entity_id=cid,
                        mismatch_type=MismatchType.MISSING_REMOTE_ORDER,
                        severity="CRITICAL",
                        local_state=local_ord.status.value,
                        exchange_state="NOT_FOUND",
                        message=f"Local open order {cid} does not exist on exchange",
                    )
                    discrepancies.append(disc)
                    requires_freeze = True
                    self.order_repo.update_order_status(
                        client_order_id=cid,
                        status=OrderStatus.EXPIRED,
                    )

        # Detect Remote Open Orders Missing Locally
        for ex_cid, ex_ord in ex_order_map.items():
            if ex_cid not in processed_ex_cids:
                disc = Discrepancy(
                    entity_type="order",
                    entity_id=ex_cid,
                    mismatch_type=MismatchType.MISSING_LOCAL_ORDER,
                    severity="WARNING",
                    local_state="NONE",
                    exchange_state=f"{ex_ord.status.value} {ex_ord.quantity}",
                    message=f"Exchange order {ex_cid} missing locally. Created record.",
                )
                discrepancies.append(disc)
                # Create missing order locally
                self.order_repo.save_order(ex_ord)

        # 5. Reconcile Positions
        ex_pos_map: dict[str, Position] = {p.symbol: p for p in ex_positions}
        local_pos_map: dict[str, Position] = {p.symbol: p for p in local_positions}

        all_symbols = set(ex_pos_map.keys()) | set(local_pos_map.keys())
        for sym in all_symbols:
            loc_p = local_pos_map.get(sym)
            ex_p = ex_pos_map.get(sym)

            if loc_p is not None and ex_p is not None:
                if loc_p.quantity != ex_p.quantity or loc_p.side != ex_p.side:
                    disc = Discrepancy(
                        entity_type="position",
                        entity_id=sym,
                        mismatch_type=MismatchType.POSITION_MISMATCH,
                        severity="CRITICAL",
                        local_state=f"{loc_p.side.value} {loc_p.quantity}",
                        exchange_state=f"{ex_p.side.value} {ex_p.quantity}",
                        message=f"Position mismatch for symbol {sym}",
                    )
                    discrepancies.append(disc)
                    requires_freeze = True
            elif loc_p is not None and ex_p is None:
                disc = Discrepancy(
                    entity_type="position",
                    entity_id=sym,
                    mismatch_type=MismatchType.POSITION_MISMATCH,
                    severity="CRITICAL",
                    local_state=f"{loc_p.side.value} {loc_p.quantity}",
                    exchange_state="NONE",
                    message=f"Local position for {sym} missing from exchange",
                )
                discrepancies.append(disc)
                requires_freeze = True
            elif loc_p is None and ex_p is not None:
                disc = Discrepancy(
                    entity_type="position",
                    entity_id=sym,
                    mismatch_type=MismatchType.POSITION_MISMATCH,
                    severity="CRITICAL",
                    local_state="NONE",
                    exchange_state=f"{ex_p.side.value} {ex_p.quantity}",
                    message=f"Exchange position for {sym} missing from local DB",
                )
                discrepancies.append(disc)
                requires_freeze = True

        # 6. Audit Logging & System Event Recording
        if self.system_event_repo is not None:
            for disc in discrepancies:
                self.system_event_repo.record_event(
                    event_type="RECONCILIATION_DISCREPANCY",
                    severity=disc.severity,
                    source="reconciliation_engine",
                    message=disc.message,
                    metadata=disc.model_dump(),
                )

        # 7. Trigger FREEZE if critical financial mismatch detected
        if requires_freeze:
            logger.critical("Critical financial discrepancy detected! Triggering system FREEZE.")
            if self.freeze_callback is not None:
                self.freeze_callback("RECONCILIATION_CRITICAL_DISCREPANCY")

        report = ReconciliationReport(
            is_clean=len(discrepancies) == 0,
            requires_freeze=requires_freeze,
            discrepancies=discrepancies,
            orders_reconciled=len(local_orders),
            positions_reconciled=len(all_symbols),
            timestamp_str="",
        )

        return report

    async def run_startup_reconciliation(self) -> ReconciliationReport:
        """Run mandatory startup reconciliation during system process start or reopen."""
        logger.info("Executing mandatory startup reconciliation loop...")
        return await self.reconcile()


__all__ = ["Discrepancy", "MismatchType", "ReconciliationEngine", "ReconciliationReport"]
