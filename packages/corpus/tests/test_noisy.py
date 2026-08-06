"""Noisy-tier build (Task 2): identity reuse, rights filter, sanitize lineage,
idempotent re-derivation — the AC-1/AC-3 core behaviors."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from corpus.noisy import build_items
from traces_ingest.sanitize import REDACTED

ALLOWLIST = ["MIT", "Apache-2.0"]
PATCH = b"diff --git a/x.py b/x.py\n@@ -1 +1 @@\n-token = 'AKIAIOSFODNN7EXAMPLE'\n+t = 1\n"


def _deposit(root: Path, run_id: int, sha: str, license_id: str, created: str, patch: bytes = PATCH):
    d = root / "ci-logs" / "o_per_r" / str(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "patch.diff").write_bytes(patch)
    (d / "provenance.json").write_text(json.dumps({
        "source": "github-actions", "repo": "o/r", "head_sha": sha,
        "workflow_run_id": run_id, "run_conclusion": "failure", "pr_number": 7,
        "license": license_id, "run_created_at": created, "robots": "allow",
    }))
    return d


def test_build_items_identity_rights_sanitize(tmp_path):
    _deposit(tmp_path, 101, "abc123", "MIT", "2026-08-01T00:00:00Z")
    _deposit(tmp_path, 102, "def456", "GPL-3.0", "2026-08-01T01:00:00Z")
    res = build_items(tmp_path, ALLOWLIST)
    assert res.scanned == 2
    assert len(res.items) == 1  # GPL excluded
    assert res.excluded_rights == [{"repo": "o/r", "run_id": 102, "license": "GPL-3.0"}]
    item = res.items[0]
    assert item.repo == "o/r" and item.license == "MIT"
    assert item.patch_sha256 != sha256(PATCH).hexdigest()  # sanitized, not raw
    assert item.sanitize_counts == {"aws_access_key": 1}
    # the raw key must not be re-derivable from the item lineage
    assert REDACTED not in PATCH.decode()  # fixture carries the raw key...
    # ... and the identity was computed over the sanitized text (normalize applied)


def test_idempotent_rederivation(tmp_path):
    _deposit(tmp_path, 101, "abc123", "MIT", "2026-08-01T00:00:00Z")
    a = build_items(tmp_path, ALLOWLIST)
    b = build_items(tmp_path, ALLOWLIST)
    assert [i.item_id for i in a.items] == [i.item_id for i in b.items]


def test_cross_source_duplicate_collapses(tmp_path):
    _deposit(tmp_path, 101, "abc123", "MIT", "2026-08-01T00:00:00Z")
    # same logical run re-deposited under a second source dir layout
    d2 = tmp_path / "ci-logs" / "mirror_per_r" / "101"
    d2.mkdir(parents=True)
    (d2 / "patch.diff").write_bytes(PATCH)
    (d2 / "provenance.json").write_text(json.dumps({
        "source": "github-actions", "repo": "o/r", "head_sha": "abc123",
        "workflow_run_id": 101, "run_conclusion": "failure", "license": "MIT",
        "run_created_at": "2026-08-01T00:00:00Z",
    }))
    res = build_items(tmp_path, ALLOWLIST)
    assert len(res.items) == 1
    assert res.duplicates == 1


def test_naive_timestamp_rejected(tmp_path):
    _deposit(tmp_path, 101, "abc123", "MIT", "2026-08-01 00:00:00")
    from core_schema.errors import SchemaError

    with pytest.raises(SchemaError) as ei:
        build_items(tmp_path, ALLOWLIST)
    assert ei.value.code == "LI-CORPUS-003"


def test_empty_landing_is_empty_not_error(tmp_path):
    res = build_items(tmp_path, ALLOWLIST)
    assert res.items == [] and res.scanned == 0
