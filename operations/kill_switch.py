"""System Kill Switch Manager Module.

Provides authoritative emergency kill switch controls, state management,
and audit logging.

Rule: The kill switch must be ACTIVE for order submission or trade authorization.
Any SOFT_KILL or HARD_KILL state causes immediate FREEZE.
See architecture.md §28 and implementation_spec.md §16.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from adapters.repositories.sqlite_repos import SystemEventRepository
from core.domain.enums import EventType, KillSwitchState, Severity
from core.domain.events import AuditEvent
from core.logging import get_logger

logger = get_logger(__name__)


class KillSwitchManager:
    """Authoritative System Kill Switch Controller."""

    def __init__(
        self,
        event_repo: SystemEventRepository | None = None,
        initial_state: KillSwitchState = KillSwitchState.ACTIVE,
    ) -> None:
        self.state = initial_state
        self.event_repo = event_repo
        self.last_toggled_at: datetime = datetime.now(UTC)
        self.last_reason: str = "System Initialized"
        self.toggled_by: str = "system"

    @property
    def is_active(self) -> bool:
        """Return True if system trading is permitted (ACTIVE), False if halted."""
        return self.state == KillSwitchState.ACTIVE

    def engage(self, reason: str = "Emergency Kill Switch Activated", source: str = "operator") -> None:
        """Engage the hard kill switch, halting all automated execution immediately."""
        self.state = KillSwitchState.HARD_KILL
        self.last_toggled_at = datetime.now(UTC)
        self.last_reason = reason
        self.toggled_by = source

        logger.critical(f"HARD KILL SWITCH ENGAGED: source={source}, reason={reason}")

        if self.event_repo is not None:
            event = AuditEvent(
                event_id=f"EVT-KS-{int(self.last_toggled_at.timestamp() * 1000)}",
                event_type=EventType.KILL_SWITCH_ACTIVATED,
                severity=Severity.CRITICAL,
                source=source,
                message=f"System Kill Switch engaged: {reason}",
                metadata={"state": self.state.value, "reason": reason, "toggled_by": source},
                timestamp=self.last_toggled_at,
            )
            try:
                self.event_repo.save(event)
            except Exception as exc:
                logger.error(f"Failed to record kill switch audit event: {exc}")

    def release(self, reason: str = "Kill switch reset by authorized operator", source: str = "operator") -> None:
        """Release the kill switch, returning the system to ACTIVE trading state."""
        self.state = KillSwitchState.ACTIVE
        self.last_toggled_at = datetime.now(UTC)
        self.last_reason = reason
        self.toggled_by = source

        logger.warning(f"KILL SWITCH RELEASED: source={source}, reason={reason}")

        if self.event_repo is not None:
            event = AuditEvent(
                event_id=f"EVT-KS-{int(self.last_toggled_at.timestamp() * 1000)}",
                event_type=EventType.STATE_TRANSITION,
                severity=Severity.WARNING,
                source=source,
                message=f"System Kill Switch released: {reason}",
                metadata={"state": self.state.value, "reason": reason, "toggled_by": source},
                timestamp=self.last_toggled_at,
            )
            try:
                self.event_repo.save(event)
            except Exception as exc:
                logger.error(f"Failed to record kill switch release audit event: {exc}")

    def get_status(self) -> dict[str, Any]:
        """Return operational status summary of the kill switch."""
        return {
            "state": self.state.value,
            "is_active": self.is_active,
            "last_toggled_at": self.last_toggled_at.isoformat(),
            "last_reason": self.last_reason,
            "toggled_by": self.toggled_by,
        }


__all__ = ["KillSwitchManager"]
