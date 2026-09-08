"""Operational Monitoring & Telemetry Module.

Collects real-time operational telemetry, order latency, proposal approval rates,
and execution metrics for the Trader Control Center.
See architecture.md §27 and implementation_spec.md §16.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class OperationalTelemetry:
    """Real-time operational metrics snapshot."""

    session_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    proposals_received: int = 0
    proposals_approved: int = 0
    proposals_rejected: int = 0
    proposals_frozen: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0
    orders_cancelled: int = 0
    orders_rejected: int = 0
    reconciliations_run: int = 0
    reconciliation_mismatches: int = 0
    execution_latencies_ms: list[float] = field(default_factory=list)

    @property
    def approval_rate_pct(self) -> float:
        if self.proposals_received == 0:
            return 0.0
        return (self.proposals_approved / self.proposals_received) * 100.0

    @property
    def fill_rate_pct(self) -> float:
        if self.orders_submitted == 0:
            return 0.0
        return (self.orders_filled / self.orders_submitted) * 100.0

    @property
    def avg_latency_ms(self) -> float:
        if not self.execution_latencies_ms:
            return 0.0
        return statistics.mean(self.execution_latencies_ms)

    @property
    def p95_latency_ms(self) -> float:
        if not self.execution_latencies_ms:
            return 0.0
        if len(self.execution_latencies_ms) < 20:
            return max(self.execution_latencies_ms)
        sorted_lat = sorted(self.execution_latencies_ms)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[idx]

    def record_proposal(self, decision: str) -> None:
        self.proposals_received += 1
        dec_upper = decision.upper()
        if dec_upper == "APPROVED":
            self.proposals_approved += 1
        elif dec_upper == "FREEZE":
            self.proposals_frozen += 1
        else:
            self.proposals_rejected += 1

    def record_order(self, status: str, latency_ms: float | None = None) -> None:
        self.orders_submitted += 1
        if latency_ms is not None and latency_ms > 0:
            self.execution_latencies_ms.append(latency_ms)

        stat_upper = status.upper()
        if stat_upper == "FILLED":
            self.orders_filled += 1
        elif stat_upper == "CANCELLED":
            self.orders_cancelled += 1
        elif stat_upper in ("REJECTED", "EXCHANGE_REJECTED"):
            self.orders_rejected += 1

    def record_reconciliation(self, clean: bool, mismatches_count: int = 0) -> None:
        self.reconciliations_run += 1
        if not clean:
            self.reconciliation_mismatches += mismatches_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_start": self.session_start.isoformat(),
            "proposals_received": self.proposals_received,
            "proposals_approved": self.proposals_approved,
            "proposals_rejected": self.proposals_rejected,
            "approval_rate_pct": round(self.approval_rate_pct, 2),
            "orders_submitted": self.orders_submitted,
            "orders_filled": self.orders_filled,
            "fill_rate_pct": round(self.fill_rate_pct, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "reconciliations_run": self.reconciliations_run,
            "reconciliation_mismatches": self.reconciliation_mismatches,
        }


class OperationalMonitor:
    """Operational Monitor Service for tracking system telemetry."""

    def __init__(self) -> None:
        self.telemetry = OperationalTelemetry()

    def get_metrics(self) -> dict[str, Any]:
        return self.telemetry.to_dict()


__all__ = ["OperationalMonitor", "OperationalTelemetry"]
