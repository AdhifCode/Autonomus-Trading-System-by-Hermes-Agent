"""Audit event domain model.

All state transitions and significant events are logged as AuditEvents.
The audit log is append-only, never deleted (implementation_spec §19).

See implementation_spec.md §10.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.domain.enums import EventType, Severity


class AuditEvent(BaseModel):
    """An auditable system event.

    Every significant action (trade, risk decision, state transition,
    system error) is captured as an AuditEvent for the audit trail.
    """

    event_id: str = Field(min_length=1)
    event_type: EventType
    severity: Severity
    source: str = Field(min_length=1, description="Component that generated the event")
    entity_type: str | None = None
    entity_id: str | None = None
    message: str = Field(min_length=1)
    metadata: dict[str, object] | None = None
    timestamp: datetime
