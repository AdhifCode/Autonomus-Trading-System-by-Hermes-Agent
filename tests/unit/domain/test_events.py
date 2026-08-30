"""Tests for core.domain.events — AuditEvent model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.domain.enums import EventType, Severity
from core.domain.events import AuditEvent

_NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _event(**kw):
    d = {
        "event_id": "EVT-001",
        "event_type": "TRADE_PROPOSED",
        "severity": "INFO",
        "source": "risk_engine",
        "message": "Trade proposal PRP-20260828-000001 received",
        "timestamp": _NOW.isoformat(),
    }
    d.update(kw)
    return d


class TestAuditEventValid:
    def test_basic(self):
        e = AuditEvent(**_event())
        assert e.event_type == EventType.TRADE_PROPOSED
        assert e.severity == Severity.INFO

    def test_with_entity(self):
        e = AuditEvent(
            **_event(
                entity_type="trade",
                entity_id="TRD-20260828-000001",
            )
        )
        assert e.entity_type == "trade"
        assert e.entity_id == "TRD-20260828-000001"

    def test_with_metadata(self):
        e = AuditEvent(**_event(metadata={"proposal_id": "PRP-001"}))
        assert e.metadata is not None
        assert e.metadata["proposal_id"] == "PRP-001"

    def test_optional_fields_default_none(self):
        e = AuditEvent(**_event())
        assert e.entity_type is None
        assert e.entity_id is None
        assert e.metadata is None


class TestAuditEventInvalid:
    def test_empty_event_id(self):
        with pytest.raises(ValidationError):
            AuditEvent(**_event(event_id=""))

    def test_empty_source(self):
        with pytest.raises(ValidationError):
            AuditEvent(**_event(source=""))

    def test_empty_message(self):
        with pytest.raises(ValidationError):
            AuditEvent(**_event(message=""))

    def test_invalid_event_type(self):
        with pytest.raises(ValidationError):
            AuditEvent(**_event(event_type="INVALID_EVENT"))

    def test_invalid_severity(self):
        with pytest.raises(ValidationError):
            AuditEvent(**_event(severity="FATAL"))


class TestAuditEventSerialization:
    def test_json_round_trip(self):
        original = AuditEvent(
            **_event(
                entity_type="trade",
                entity_id="T-001",
                metadata={"key": "value"},
            )
        )
        restored = AuditEvent.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_dict_round_trip(self):
        original = AuditEvent(**_event())
        restored = AuditEvent(**original.model_dump())
        assert restored == original
