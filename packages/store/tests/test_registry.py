"""Registry tests (Story 1.7)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from core_schema.errors import SchemaError
from store.registry import OriginClass, SourceEntry, audit_source, load_registry

VALID = {
    "source_id": "swe-smith-trajectories",
    "origin_class": "public_trajectory_collection",
    "license": "MIT",
    "usage_rights": "analysis + derivative labels redistribution",
    "covered_families": ["swe-agent"],
    "covered_generations": ["2025"],
    "snapshot_content_hash": "a" * 64,
    "coverage_gaps": ["no 2023 model generations"],
    "source_version": 1,
    "registered_at": "2026-08-05T10:00:00Z",
    "notes": "",
}


def _write(tmp_path: Path, sources: list[dict]) -> Path:
    p = tmp_path / "sources.yaml"
    p.write_text(yaml.safe_dump({"sources": sources}))
    return p


def test_valid_registry_loads(tmp_path):
    reg = load_registry(_write(tmp_path, [VALID]))
    e = reg["swe-smith-trajectories"]
    assert e.origin_class is OriginClass.PUBLIC_TRAJECTORY_COLLECTION


def test_all_three_origin_classes_accepted(tmp_path):
    srcs = [
        dict(VALID, source_id="own", origin_class="own_harbor_run"),
        dict(VALID, source_id="public-ci", origin_class="public_ci_logs"),
        VALID,
    ]
    reg = load_registry(_write(tmp_path, srcs))
    assert len(reg) == 3


def test_invalid_entry_typed_error(tmp_path):
    bad = dict(VALID, snapshot_content_hash="not-a-sha")
    with pytest.raises(SchemaError) as exc:
        load_registry(_write(tmp_path, [bad]))
    assert exc.value.code == "LI-REGISTRY-001"


def test_duplicate_id_rejected(tmp_path):
    with pytest.raises(SchemaError) as exc:
        load_registry(_write(tmp_path, [VALID, dict(VALID)]))
    assert exc.value.code == "LI-REGISTRY-003"


def test_audit_mutation_detected():
    e = SourceEntry.model_validate(VALID)
    assert audit_source(e, "a" * 64) == "unchanged"
    assert audit_source(e, "b" * 64) == "mutated"
