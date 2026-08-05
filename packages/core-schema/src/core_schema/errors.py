"""Typed errors for core_schema, code-allocated per conventions (LI-<PKG>-nnn).

Allocation catalog:

| Code | Raised when |
| --- | --- |
| LI-SCHEMA-001 | Store envelope missing/unsupported ``schema_version`` |
| LI-SCHEMA-002 | naive datetime where a tz-aware instant is required |
| LI-SCHEMA-003 | ATIF agent-only field present on a non-agent step |
| LI-SCHEMA-004 | observation references an unknown tool_call_id |
| LI-SCHEMA-005 | step_id sequence broken (must start at 1, sequential) |
| LI-SCHEMA-006 | content-derived id mismatch (e.g. task_id vs content) |
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class SchemaError(Exception):
    """Typed schema/validation error carrying a stable code and context."""

    def __init__(self, code: str, message: str, ctx: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.ctx = ctx or {}

    def __str__(self) -> str:
        return f"{self.code}: {self.message} | ctx={self.ctx}"


def ensure_aware_utc(value: datetime, field: str = "timestamp") -> datetime:
    """Normalize to UTC. Naive datetimes are undefined across multi-source
    ingestion, so they raise LI-SCHEMA-002; aware non-UTC converts."""
    if not isinstance(value, datetime):
        raise SchemaError(
            "LI-SCHEMA-002", f"{field}: expected datetime", {"got": type(value).__name__}
        )
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise SchemaError(
            "LI-SCHEMA-002",
            f"{field}: naive datetime; tz-aware required (aware non-UTC is normalized to UTC)",
            {"value": value.isoformat()},
        )
    return value.astimezone(UTC)
