"""Operational Audit Trail & Event Logging Module.

Provides query and recording interfaces for immutable audit logs in SQLite.
All risk rejections, state machine transitions, emergency kill switch events,
and UI operational commands must be logged for auditability and post-mortem analysis.

See architecture.md §29 and implementation_spec.md §17.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from adapters.repositories.sqlite_repos import SystemEventRepository
from core.domain.enums import EventType, Severity
from core.domain.events import AuditEvent
from core.logging import get_logger

logger = get_logger(__name__)


class AuditLogger:
    """Operational Audit Logger and Query Engine."""

    def __init__(self, repo: SystemEventRepository) -> None:
        self.repo = repo

    def record_event(
        self,
        event_type: EventType | str,
        message: str,
        severity: Severity = Severity.INFO,
        source: str = "operations",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Create and persist an AuditEvent record."""
        now = datetime.now(UTC)
        ev_type = EventType(event_type) if isinstance(event_type, str) else event_type

        event = AuditEvent(
            event_id=f"EVT-{int(now.timestamp() * 1000)}",
            timestamp=now,
            event_type=ev_type,
            severity=severity,
            source=source,
            message=message,
            metadata=metadata or {},
        )

        self.repo.save(event)
        return event

    def list_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch recent audit trail records from repository."""
        events = self.repo.get_all()
        return events[:limit]

    def filter_by_severity(self, min_severity: Severity = Severity.WARNING) -> list[dict[str, Any]]:
        """Filter audit trail events by minimum severity level."""
        all_events = self.repo.get_all()
        severity_ranks = {
            Severity.INFO.value: 2,
            Severity.WARNING.value: 3,
            Severity.ERROR.value: 4,
            Severity.CRITICAL.value: 5,
        }
        threshold = severity_ranks.get(min_severity.value, 2)
        return [
            e for e in all_events
            if severity_ranks.get(str(e.get("severity", "INFO")), 1) >= threshold
        ]


__all__ = ["AuditLogger"]
