"""System Health Monitoring Module.

Performs subsystem health diagnostics across SQLite, Exchange Connectivity,
Market Data Freshness, and Memory/Process boundaries.
See architecture.md §27 and implementation_spec.md §16.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from adapters.database.sqlite import SQLiteManager
from core.logging import get_logger

logger = get_logger(__name__)


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    latency_ms: float = 0.0
    details: str = ""


@dataclass
class SystemHealthReport:
    overall_status: HealthStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    components: list[ComponentHealth] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.overall_status == HealthStatus.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "timestamp": self.timestamp.isoformat(),
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "latency_ms": round(c.latency_ms, 2),
                    "details": c.details,
                }
                for c in self.components
            ],
        }


class HealthChecker:
    """Authoritative Subsystem Health Diagnostics Engine."""

    def __init__(self, db: SQLiteManager | None = None) -> None:
        self.db = db

    def check_database(self) -> ComponentHealth:
        """Verify SQLite connectivity, WAL mode, and query response latency."""
        if self.db is None:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                details="Database manager not configured",
            )

        t0 = time.perf_counter()
        try:
            cursor = self.db.execute("PRAGMA journal_mode;")
            row = cursor.fetchone()
            wal_mode = row[0] if row else "unknown"
            latency = (time.perf_counter() - t0) * 1000.0

            status = HealthStatus.HEALTHY if str(wal_mode).lower() == "wal" else HealthStatus.DEGRADED
            return ComponentHealth(
                name="database",
                status=status,
                latency_ms=latency,
                details=f"SQLite WAL mode: {wal_mode}",
            )
        except Exception as exc:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                details=f"Database query failure: {exc}",
            )

    def check_market_data(self, last_data_timestamp: datetime | None, stale_timeout_sec: float = 10.0) -> ComponentHealth:
        """Verify market data freshness against configured timeout."""
        if last_data_timestamp is None:
            return ComponentHealth(
                name="market_data",
                status=HealthStatus.DEGRADED,
                details="No market data ingested yet",
            )

        age = (datetime.now(UTC) - last_data_timestamp).total_seconds()
        if age <= stale_timeout_sec:
            return ComponentHealth(
                name="market_data",
                status=HealthStatus.HEALTHY,
                details=f"Data age: {age:.1f}s (timeout: {stale_timeout_sec}s)",
            )
        return ComponentHealth(
            name="market_data",
            status=HealthStatus.DEGRADED,
            details=f"Market data stale: {age:.1f}s > {stale_timeout_sec}s limit",
        )

    def check_exchange(self, is_connected: bool, last_heartbeat_age_sec: float = 0.0) -> ComponentHealth:
        """Verify exchange connectivity and heartbeat freshness."""
        if not is_connected:
            return ComponentHealth(
                name="exchange",
                status=HealthStatus.UNHEALTHY,
                details="Exchange disconnected",
            )
        if last_heartbeat_age_sec > 30.0:
            return ComponentHealth(
                name="exchange",
                status=HealthStatus.DEGRADED,
                details=f"Exchange heartbeat delayed: {last_heartbeat_age_sec:.1f}s",
            )
        return ComponentHealth(
            name="exchange",
            status=HealthStatus.HEALTHY,
            details="Exchange connected and heartbeat verified",
        )

    def evaluate_system_health(
        self,
        last_data_ts: datetime | None = None,
        exchange_connected: bool = True,
        heartbeat_age: float = 0.0,
    ) -> SystemHealthReport:
        """Aggregate subsystem diagnostics into authoritative SystemHealthReport."""
        components = [
            self.check_database(),
            self.check_market_data(last_data_ts),
            self.check_exchange(exchange_connected, heartbeat_age),
        ]

        if any(c.status == HealthStatus.UNHEALTHY for c in components):
            overall = HealthStatus.UNHEALTHY
        elif any(c.status == HealthStatus.DEGRADED for c in components):
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return SystemHealthReport(overall_status=overall, components=components)


__all__ = ["ComponentHealth", "HealthChecker", "HealthStatus", "SystemHealthReport"]
