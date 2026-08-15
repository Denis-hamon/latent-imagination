"""Deployer-local workload history builder (story 7.2): identity-join protocol
with the raw-vs-normalized sha trap, denominator honesty, poison discipline."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from core_schema.identity import normalize_diff
from gate_adapters.workload_history import build_workload_history

DIFF_NORMAL = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-x\n+y\n"
DIFF_RAW = DIFF_NORMAL.replace("\n", "\r\n") + "   "  # NOT in normal form


def _sha(s: str) -> str:
    return sha256(s.encode()).hexdigest()


def _store(tmp_path: Path, *, snapshots: list[list[dict]], labels: list[list[dict]],
           poison_labels: bool = False) -> Path:
    store = tmp_path / "store"
    store.mkdir(parents=True, exist_ok=True)
    for i, rows in enumerate(snapshots):
        d = store / "canonical" / f"snap-{i}" / "v0"
        d.mkdir(parents=True)
        (d / f"snapshot-snap-{i}.json").write_text(json.dumps(rows))
    for i, rows in enumerate(labels):
        d = store / "labels" / f"labels-{i:03d}" / "v0"
        d.mkdir(parents=True)
        (d / "labels-rules-v1.json").write_text(json.dumps(rows))
    if poison_labels:
        d = store / "labels" / "labels-poison" / "v0"
        d.mkdir(parents=True)
        (d / "labels-rules-v1.json").write_text("{not json")
    return store


def _log(tmp_path: Path, events: list[dict]) -> Path:
    p = tmp_path / "decisions.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return p


def _annotated(patch_sha: str, prob: float, tier: str = "diff_touched", **payload_extra) -> dict:
    return {"schema_version": 1, "kind": "gate_annotated",
            "occurred_at": "2026-08-15T10:00:00Z",
            "payload": {"candidate": {"patch_sha256": patch_sha},
                        "flip_probability": prob,
                        "prediction_target_tier": tier, **payload_extra}}


def _snap_row(attempt_id: str, patch_sha: str) -> dict:
    return {"attempt_id": attempt_id, "task_id": "t1", "patch_sha256": patch_sha}


def _label(attempt_id: str, outcome: str) -> dict:
    return {"attempt_id": attempt_id, "task_id": "t1", "outcome": outcome,
            "schema_version": 1, "ruleset_version": "rules-v1"}


class TestJoinProtocol:
    def test_full_chain_joins(self, tmp_path):
        h = _sha(DIFF_NORMAL)
        store = _store(tmp_path, snapshots=[[_snap_row("att-1", h)]],
                       labels=[[_label("att-1", "valid_execution")]])
        rep = build_workload_history(_log(tmp_path, [_annotated(h, 0.9)]), store)
        assert rep.n_matched == 1
        assert rep.rows[0] == {"patch_sha256": h, "flip_probability": 0.9,
                               "prediction_target_tier": "diff_touched",
                               "outcome": "valid_execution"}
        assert rep.n_unmatched == rep.n_ambiguous == rep.n_abstentions == 0

    def test_identity_trap_raw_vs_normalized_sha_is_excluded_not_faked(self, tmp_path):
        """The decision logs the RAW diff sha; the snapshot carries the
        normalize_diff sha. They differ here -> the annotation cannot join and
        is counted unmatched (denominator never invented, OQ-10)."""
        raw_sha, norm_sha = _sha(DIFF_RAW), _sha(normalize_diff(DIFF_RAW))
        assert raw_sha != norm_sha  # the trap is real for this diff
        store = _store(tmp_path, snapshots=[[_snap_row("att-1", norm_sha)]],
                       labels=[[_label("att-1", "valid_execution")]])
        rep = build_workload_history(_log(tmp_path, [_annotated(raw_sha, 0.9)]), store)
        assert rep.n_matched == 0
        assert rep.n_unmatched == 1

    def test_snapshot_join_but_no_label_is_unmatched(self, tmp_path):
        h = _sha(DIFF_NORMAL)
        store = _store(tmp_path, snapshots=[[_snap_row("att-1", h)]], labels=[[]])
        rep = build_workload_history(_log(tmp_path, [_annotated(h, 0.9)]), store)
        assert rep.n_unmatched == 1 and rep.n_matched == 0

    def test_conflicting_labels_are_ambiguous_not_guessed(self, tmp_path):
        h = _sha(DIFF_NORMAL)
        store = _store(tmp_path,
                       snapshots=[[_snap_row("att-1", h), _snap_row("att-2", h)]],
                       labels=[[_label("att-1", "valid_execution"),
                                _label("att-2", "false_start_tests_ran_no_flip")]])
        rep = build_workload_history(_log(tmp_path, [_annotated(h, 0.9)]), store)
        assert rep.n_matched == 0
        assert rep.n_ambiguous == 1  # exact count: one annotation, one
        # ambiguity (epic-7 review patch 3 — conflicting attempts count once,
        # not once per attempt; the loose >= 1 would let double-counting back in)

    def test_abstentions_counted_and_excluded(self, tmp_path):
        h = _sha(DIFF_NORMAL)
        store = _store(tmp_path, snapshots=[[_snap_row("att-1", h)]],
                       labels=[[_label("att-1", "valid_execution")]])
        log = _log(tmp_path, [
            _annotated(h, 0.9),
            {"schema_version": 1, "kind": "prediction_refused",
             "occurred_at": "2026-08-15T10:01:00Z",
             "payload": {"reason": "no F2P denominator (OQ-10 abstain)"}},
        ])
        rep = build_workload_history(log, store)
        assert rep.n_abstentions == 1 and rep.n_matched == 1

    def test_malformed_annotation_shapes_counted(self, tmp_path):
        h = _sha(DIFF_NORMAL)
        store = _store(tmp_path, snapshots=[[_snap_row("att-1", h)]],
                       labels=[[_label("att-1", "valid_execution")]])
        log = _log(tmp_path, [
            _annotated(h, True),            # bool probability
            _annotated(h, 0.9, tier="invented"),  # unknown tier
            {"schema_version": 1, "kind": "gate_annotated",
             "occurred_at": "2026-08-15T10:02:00Z", "payload": "not-a-dict"},
        ])
        rep = build_workload_history(log, store)
        assert rep.n_malformed == 3 and rep.n_matched == 0


class TestPoisonDiscipline:
    def test_torn_line_counted_by_loader_others_survive(self, tmp_path):
        h = _sha(DIFF_NORMAL)
        store = _store(tmp_path, snapshots=[[_snap_row("att-1", h)]],
                       labels=[[_label("att-1", "valid_execution")]])
        log = tmp_path / "decisions.jsonl"
        log.write_text('{"torn\n' + json.dumps(_annotated(h, 0.9)) + "\n")
        rep = build_workload_history(log, store)
        assert rep.n_matched == 1  # torn line skipped, never a crash

    def test_bom_tolerated(self, tmp_path):
        h = _sha(DIFF_NORMAL)
        store = _store(tmp_path, snapshots=[[_snap_row("att-1", h)]],
                       labels=[[_label("att-1", "valid_execution")]])
        log = tmp_path / "decisions.jsonl"
        log.write_bytes(b"\xef\xbb\xbf" + json.dumps(_annotated(h, 0.9)).encode() + b"\n")
        assert build_workload_history(log, store).n_matched == 1

    def test_poison_label_file_counted_not_fatal(self, tmp_path):
        h = _sha(DIFF_NORMAL)
        store = _store(tmp_path, snapshots=[[_snap_row("att-1", h)]],
                       labels=[[_label("att-1", "valid_execution")]], poison_labels=True)
        rep = build_workload_history(_log(tmp_path, [_annotated(h, 0.9)]), store)
        assert rep.n_matched == 1
        assert rep.n_poison_files >= 1


class TestFailClosedInputs:
    def test_missing_store(self, tmp_path):
        log = _log(tmp_path, [_annotated("a" * 64, 0.9)])
        with pytest.raises(SchemaError) as ei:
            build_workload_history(log, tmp_path / "nowhere")
        assert ei.value.code == "LI-GADPT-005"

    def test_missing_decisions_log(self, tmp_path):
        store = _store(tmp_path, snapshots=[], labels=[])
        with pytest.raises(SchemaError) as ei:
            build_workload_history(tmp_path / "nope.jsonl", store)
        assert ei.value.code == "LI-GADPT-004"
