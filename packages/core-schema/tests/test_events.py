"""StoreEvent envelope: schema v1 gate (LI-SCHEMA-001)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from core_schema.errors import SchemaError
from core_schema.events import StoreEvent

NOW = datetime(2026, 8, 5, 10, 0, 0, tzinfo=UTC)


class TestEnvelopeGate:
    def test_valid_envelope(self):
        ev = StoreEvent.parse(
            {
                "schema_version": 1,
                "kind": "attempt_labeled",
                "occurred_at": NOW.isoformat(),
                "payload": {"attempt_id": "x" * 64},
            }
        )
        assert ev.schema_version == 1

    def test_missing_schema_version(self):
        with pytest.raises(SchemaError) as exc:
            StoreEvent.parse({"kind": "attempt_labeled", "occurred_at": NOW.isoformat(), "payload": {}})
        assert exc.value.code == "LI-SCHEMA-001"

    def test_wrong_schema_version(self):
        with pytest.raises(SchemaError) as exc:
            StoreEvent.parse(
                {
                    "schema_version": 2,
                    "kind": "attempt_labeled",
                    "occurred_at": NOW.isoformat(),
                    "payload": {},
                }
            )
        assert exc.value.code == "LI-SCHEMA-001"

    def test_naive_occurred_at(self):
        with pytest.raises(SchemaError) as exc:
            StoreEvent.parse(
                {
                    "schema_version": 1,
                    "kind": "attempt_labeled",
                    "occurred_at": "2026-08-05T10:00:00",
                    "payload": {},
                }
            )
        assert exc.value.code == "LI-SCHEMA-002"

    def test_kind_must_be_snake_case(self):
        with pytest.raises(SchemaError) as exc:
            StoreEvent.parse(
                {
                    "schema_version": 1,
                    "kind": "Attempt Labeled",
                    "occurred_at": NOW.isoformat(),
                    "payload": {},
                }
            )
        assert exc.value.code == "LI-SCHEMA-006"
