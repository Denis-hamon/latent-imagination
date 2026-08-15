"""Deployer-local workload history builder (story 7.2, FR-21 c1).

Joins the deployer's OWN decision log (``decisions.jsonl``) with the
deployer's OWN local store (canonical snapshots + label-sets) into the
measurement rows ``gate.workload_check`` consumes. Pure read path — this
module writes NOTHING (the only write seam stays ``gate.decision_log``,
5.6 etl-seam-decision law).

Identity-join protocol (see governance/gate/workload-check-protocol.md):

  decision (gate_annotated)  --patch_sha256-->  canonical snapshot row (attempt_id)
                     snapshot row  --attempt_id-->  labels row (outcome)

THE IDENTITY TRAP (documented, tested): the decision log records
``sha256`` of the RAW reconstructed diff (``CandidateCtx.__post_init__``),
while the store's snapshot rows carry ``sha256(identity.normalize_diff(diff))``.
The two coincide only when the diff is already in normal form. A prediction
that cannot be joined through BOTH hops on exact hash equality is counted
``unmatched`` and EXCLUDED — the denominator is never invented (OQ-10, FR-3,
FR-9).

Poison discipline (5.6): torn log lines and unparseable store files are
COUNTED and skipped; a deployer's corrupted input can never turn a crash into
data loss. Abstentions (``prediction_refused``) are counted and excluded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core_schema.errors import SchemaError

from gate_adapters.telemetry_etl import load_log

TIERS = ("diff_touched", "user_designated")
OUTCOMES = ("valid_execution", "false_start_tests_ran_no_flip",
            "false_start_infrastructure_failure")


@dataclass(frozen=True)
class WorkloadHistoryReport:
    rows: tuple[dict[str, Any], ...]
    n_annotations: int
    n_matched: int
    n_unmatched: int
    n_ambiguous: int
    n_abstentions: int
    n_malformed: int
    n_poison_files: int


def _index_snapshots(store_root: Path) -> tuple[dict[str, set[str]], int]:
    """patch_sha256 -> {attempt_id, ...}; snapshots are JSON arrays of rows."""
    by_sha: dict[str, set[str]] = {}
    poison = 0
    for f in sorted(store_root.glob("canonical/**/snapshot-*.json")):
        if "manifests" in f.parts:
            continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError, OSError):
            poison += 1
            continue
        if not isinstance(rows, list):
            poison += 1
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            sha, aid = r.get("patch_sha256"), r.get("attempt_id")
            if isinstance(sha, str) and isinstance(aid, str):
                by_sha.setdefault(sha, set()).add(aid)
    return by_sha, poison


def _index_labels(store_root: Path) -> tuple[dict[str, str], set[str], int]:
    """attempt_id -> outcome; disagreement across label files = poisoned attempt.
    Returns (by_attempt, conflicts_set, poison_count) — conflicts are tracked as
    a set so the join can distinguish 'conflicting labels' from 'no labels' and
    avoid double-counting."""
    by_attempt: dict[str, str] = {}
    conflicts: set[str] = set()
    poison = 0
    for f in sorted(store_root.glob("labels/**/labels-*.json")):
        if "manifests" in f.parts:
            continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError, OSError):
            poison += 1
            continue
        if not isinstance(rows, list):
            poison += 1
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            aid, outcome = r.get("attempt_id"), r.get("outcome")
            if not (isinstance(aid, str) and outcome in OUTCOMES):
                continue
            if aid in by_attempt and by_attempt[aid] != outcome:
                conflicts.add(aid)
                by_attempt.pop(aid)  # conflicting labels: never guess
            elif aid not in by_attempt:
                by_attempt[aid] = outcome
    return by_attempt, conflicts, poison


def build_workload_history(decisions_path: Path, store_root: Path) -> WorkloadHistoryReport:
    decisions_path, store_root = Path(decisions_path), Path(store_root)
    if not store_root.is_dir():
        raise SchemaError("LI-GADPT-005", "store root missing — the workload check "
                                          "reads the deployer's local store",
                          {"path": str(store_root)})
    records, _ = load_log(decisions_path)  # LI-GADPT-004 on missing/unreadable
    snap_by_sha, snap_poison = _index_snapshots(store_root)
    label_by_attempt, label_conflicts, label_poison = _index_labels(store_root)

    rows: list[dict[str, Any]] = []
    n_annotations = n_unmatched = n_ambiguous = n_abstentions = n_malformed = 0
    for rec in records:
        kind = rec.get("kind")
        if kind == "prediction_refused":
            n_abstentions += 1
            continue
        if kind != "gate_annotated":
            continue
        n_annotations += 1
        payload = rec.get("payload")
        if not isinstance(payload, dict):
            n_malformed += 1
            continue
        cand = payload.get("candidate")
        sha = cand.get("patch_sha256") if isinstance(cand, dict) else None
        prob = payload.get("flip_probability")
        tier = payload.get("prediction_target_tier")
        if (not isinstance(sha, str)
                or isinstance(prob, bool) or not isinstance(prob, (int, float))
                or tier not in TIERS):
            n_malformed += 1
            continue
        attempts = snap_by_sha.get(sha)
        if not attempts:
            n_unmatched += 1  # no snapshot row carries this exact diff hash
            continue
        # conflicting labels for any attempt = ambiguous (not unmatched)
        if any(a in label_conflicts for a in attempts):
            n_ambiguous += 1
            continue
        outcomes = {label_by_attempt[a] for a in attempts if a in label_by_attempt}
        if len(outcomes) != 1:
            if not outcomes:
                n_unmatched += 1  # snapshot row(s) exist but none is labeled
            else:
                n_ambiguous += 1  # >1 distinct outcome across attempts
            continue
        rows.append({
            "patch_sha256": sha,
            "flip_probability": float(prob),
            "prediction_target_tier": tier,
            "outcome": next(iter(outcomes)),
        })
    return WorkloadHistoryReport(
        rows=tuple(rows),
        n_annotations=n_annotations,
        n_matched=len(rows),
        n_unmatched=n_unmatched,
        n_ambiguous=n_ambiguous,
        n_abstentions=n_abstentions,
        n_malformed=n_malformed,
        n_poison_files=snap_poison + label_poison,
    )
