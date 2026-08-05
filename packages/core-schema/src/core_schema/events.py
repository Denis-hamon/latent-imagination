"""Store event envelope — OUR schema (int version), distinct from ATIF's string
``schema_version`` carried by ExecutionTrace. Two fields, same name, unrelated
semantics; each is gated by its own validator. The README states this in print.

- schema_version: Literal[1] — ours; bump policy in packages/core-schema/README.md
- kind: past-tense snake_case event name per conventions (``attempt_labeled``…)
- occurred_at: tz-aware (naive → LI-SCHEMA-002)
- payload: tagged-union of domain models (opaque here; labelers/validators cast)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from core_schema.errors import SchemaError, ensure_aware_utc

_SNAKE_PAST = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)+$")


class StoreEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    kind: str
    occurred_at: datetime
    payload: dict[str, Any]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _v1(cls, v: Any) -> Any:
        if v != 1:
            raise SchemaError(
                "LI-SCHEMA-001",
                "store event schema_version must be 1",
                {"got": v},
            )
        return v

    @field_validator("occurred_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return ensure_aware_utc(v, "occurred_at")

    @field_validator("kind")
    @classmethod
    def _snake(cls, v: str) -> str:
        if not _SNAKE_PAST.match(v):
            raise SchemaError(
                "LI-SCHEMA-006",
                "event kind must be snake_case (past-tense per conventions)",
                {"kind": v},
            )
        return v

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> StoreEvent:
        """Parse untrusted input; missing/wrong schema_version → LI-SCHEMA-001,
        surfaced BEFORE pydantic's own missing-field error so the envelope gate
        always speaks our error codes."""
        v = raw.get("schema_version")
        if v != 1:
            raise SchemaError(
                "LI-SCHEMA-001",
                "store envelope schema_version must be 1",
                {"got": v},
            )
        return cls.model_validate(raw)
