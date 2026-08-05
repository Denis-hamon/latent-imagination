"""Normalization tests: dedup precedence, rejection counts, sanitize counts."""

from __future__ import annotations

import json
from pathlib import Path

from traces_ingest.normalize import normalize_landing

TASK = {
    "repo_full_name": "django/django",
    "commit_sha": "c" * 40,
    "f2p_tests": ["tests/x.py::test_y"],
}
FP = {"os_family": "linux", "python_version": "3.12.8", "deps_lock_sha256": "f" * 64}
DIFF = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"


def _deposit(
    landing: Path, source_id: str, source_class: str, name: str,
    *, start="2026-08-05T10:00:00+00:00", extra_provenance: dict | None = None,
) -> None:
    d = landing / source_id
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps({
        "record": {
            "task": TASK,
            "patch_diff": DIFF,
            "env_fingerprint": FP,
            "attempt_start": start,
            "raw_test_output_ref": "blob://runs/1.txt",
            "provenance": extra_provenance or {},
            "source_id": source_id,
            "source_class": source_class,
        }
    }))


def test_dedup_same_attempt_two_sources(tmp_path):
    landing = tmp_path / "landing"
    _deposit(landing, "pub", "public_trajectory_collection", "a.deposit.json")
    _deposit(landing, "mine", "own_harbor_run", "b.deposit.json")
    rep = normalize_landing(landing)
    assert len(rep.accepted) == 1
    assert rep.dedup_collisions[0]["kept"] == "mine"
    assert rep.counts["dedup_dropped"] == 1


def test_distinct_attempts_both_kept(tmp_path):
    landing = tmp_path / "landing"
    _deposit(landing, "pub", "public_trajectory_collection", "a.deposit.json", start="2026-08-05T10:00:00+00:00")
    _deposit(landing, "mine", "own_harbor_run", "b.deposit.json", start="2026-08-05T11:00:00+00:00")
    rep = normalize_landing(landing)
    assert len(rep.accepted) == 2


def test_malformed_rejected_with_counts(tmp_path):
    landing = tmp_path / "landing"
    _deposit(landing, "pub", "public_trajectory_collection", "good.deposit.json")
    bad_dir = landing / "pub2"
    bad_dir.mkdir(parents=True)
    (bad_dir / "bad.deposit.json").write_text(json.dumps({"record": {"task": TASK}}))
    rep = normalize_landing(landing)
    assert len(rep.accepted) == 1
    assert rep.rejected and rep.rejected[0]["file"] == "bad.deposit.json"
    assert rep.counts["rejected_ValueError"] == 1


def test_sanitized_provenance_counts(tmp_path):
    landing = tmp_path / "landing"
    _deposit(
        landing, "pub", "public_trajectory_collection", "a.deposit.json",
        extra_provenance={"note": "token: 'abcdef0123456789abcdef'"},
    )
    rep = normalize_landing(landing)
    assert rep.counts.get("sanitized_keys", 0) >= 1
