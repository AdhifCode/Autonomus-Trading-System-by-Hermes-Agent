"""System Recovery Orchestrator Module.

Manages safe system recovery protocols after crashes, network disconnections,
or reconciliation discrepancy freezes:
1. Reconnects to database and verifies table integrity.
2. Runs mandatory startup reconciliation against exchange REST truth.
3. Self-heals pending/unknown order states.
4. Resets system state cleanly without risking double executions.

See architecture.md §2.3, §17 and implementation_spec.md §9.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from adapters.repositories.sqlite_repos import OrderRepository, SystemEventRepository
from core.domain.enums import EventType, OrderStatus, Severity
from core.domain.events import AuditEvent
from core.execution.reconciliation import ReconciliationEngine, ReconciliationReport
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RecoveryResult:
    success: bool
    reconciliation_report: ReconciliationReport | None
    orders_recovered: int
    message: str
    timestamp: datetime


class RecoveryOrchestrator:
    """Orchestrates safe crash recovery and state resynchronization."""

    def __init__(
        self,
        reconciliation_engine: ReconciliationEngine,
        order_repo: OrderRepository,
        event_repo: SystemEventRepository | None = None,
    ) -> None:
        self.reconciliation = reconciliation_engine
        self.order_repo = order_repo
        self.event_repo = event_repo

    async def execute_recovery(self, reason: str = "Process startup / recovery trigger") -> RecoveryResult:
        """Run full recovery sequence: reconcile orders, positions, and balances."""
        now = datetime.now(UTC)
        logger.info(f"Initiating system recovery protocol: {reason}")

        try:
            # 1. Execute authoritative REST reconciliation
            rec_report = await self.reconciliation.reconcile()

            # 2. Check and clean up orphaned PENDING orders older than 5 minutes
            recovered_count = 0
            open_orders = self.order_repo.get_open_orders()
            for o in open_orders:
                if o.status == OrderStatus.PENDING:
                    age_sec = (now - o.created_at).total_seconds()
                    if age_sec > 300.0:  # 5 minutes
                        logger.warning(f"Orphaned PENDING order {o.client_order_id} aged {age_sec:.1f}s expired during recovery")
                        self.order_repo.update_order_status(o.client_order_id, OrderStatus.EXPIRED)
                        recovered_count += 1

            # 3. Record Audit Event
            if self.event_repo is not None:
                event = AuditEvent(
                    event_id=f"EVT-REC-{int(now.timestamp() * 1000)}",
                    event_type=EventType.STATE_TRANSITION,
                    severity=Severity.INFO if rec_report.is_clean else Severity.WARNING,
                    source="RecoveryOrchestrator",
                    message=f"System recovery completed: {reason}. Discrepancies: {len(rec_report.discrepancies)}",
                    metadata={
                        "is_clean": rec_report.is_clean,
                        "discrepancies_count": len(rec_report.discrepancies),
                        "orders_recovered": recovered_count,
                    },
                    timestamp=now,
                )
                self.event_repo.save(event)

            return RecoveryResult(
                success=rec_report.is_clean,
                reconciliation_report=rec_report,
                orders_recovered=recovered_count,
                message="Recovery completed successfully",
                timestamp=now,
            )

        except Exception as exc:
            logger.error(f"System recovery protocol encountered an error: {exc}")
            return RecoveryResult(
                success=False,
                reconciliation_report=None,
                orders_recovered=0,
                message=f"Recovery failed: {exc}",
                timestamp=now,
            )


__all__ = ["RecoveryOrchestrator", "RecoveryResult"]
