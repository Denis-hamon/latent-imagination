"""Registry Schema (FR-1) + loader. YAML files in data/registries/."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml
from core_schema.errors import SchemaError
from pydantic import BaseModel, ConfigDict, field_validator


class OriginClass(str, Enum):
    OWN_HARBOR_RUN = "own_harbor_run"
    PUBLIC_TRAJECTORY_COLLECTION = "public_trajectory_collection"
    PUBLIC_CI_LOGS = "public_ci_logs"


class SourceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    origin_class: OriginClass
    license: str
    usage_rights: str
    covered_families: list[str]
    covered_generations: list[str]
    snapshot_content_hash: str
    coverage_gaps: list[str]
    source_version: int = 1
    registered_at: str  # occurrence metadata
    notes: str = ""
    supersedes: str | None = None

    @field_validator("snapshot_content_hash")
    @classmethod
    def _hash(cls, v: str) -> str:
        if len(v) != 64 or any(c not in "0123456789abcdef" for c in v.lower()):
            raise SchemaError(
                "LI-REGISTRY-001", "snapshot_content_hash must be sha256 hex", {"got": v}
            )
        return v


def load_registry(path: Path) -> dict[str, SourceEntry]:
    data = yaml.safe_load(Path(path).read_text())
    entries: dict[str, SourceEntry] = {}
    for raw in data.get("sources", []):
        try:
            e = SourceEntry.model_validate(raw)
        except SchemaError:
            raise
        except Exception as exc:  # pydantic validation -> typed error
            raise SchemaError(
                "LI-REGISTRY-002", f"invalid source entry: {raw.get('source_id', '?')}", {}
            ) from exc
        if e.source_id in entries:
            raise SchemaError("LI-REGISTRY-003", f"duplicate source_id {e.source_id}", {})
        entries[e.source_id] = e
    return entries


def audit_source(entry: SourceEntry, new_snapshot_hash: str) -> str:
    """'unchanged' if the content hash matches; 'mutated' otherwise (FR-1)."""
    return "unchanged" if entry.snapshot_content_hash == new_snapshot_hash else "mutated"
