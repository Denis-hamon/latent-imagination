"""Labeling runner: pure rules over canonical snapshots → label-set artifacts.

Writes via store only (WRITERS table: labeling). The ledger run row carries the
ruleset CONTENT HASH (not the version string), so precedence verification binds
to bytes, not labels (review C-3). Determinism hook: assert_replay_identical.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from prereg.ledger import append_entry, run_entry
from store.emit import write_artifact

from labeling.rules_v1 import (
    INFRA_PATTERNS,
    RULESET_VERSION,
    SCHEMA_VERSION,
    classify_tests_output,
)


class QuarantineCapExceeded(Exception):
    """The pre-registered quarantine share cap was exceeded; measurement halts."""

    code = "LI-LABEL-001"


class DuplicateRunError(Exception):
    code = "LI-LABEL-002"


def ruleset_content_hash() -> str:
    """sha256 over the canonical JSON of the rules content — the anchor object."""
    body = {
        "version": RULESET_VERSION,
        "schema_version": SCHEMA_VERSION,
        "infra_patterns": INFRA_PATTERNS,
        # classify_tests_output is code; its behavior is fixed by the module
        # bytes — hash those too, or changes without pattern-list edits escape.
        "module_bytes_sha256": sha256(
            (Path(__file__).parent / "rules_v1.py").read_bytes()
        ).hexdigest(),
    }
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canon.encode()).hexdigest()


@dataclass(frozen=True)
class LabelRun:
    label_artifact_dir: Path
    quarantine_dir: Path
    summary: dict


def _labels_bytes(labels: list[dict]) -> bytes:
    return (json.dumps(labels, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _quarantine_bytes(rows: list[dict]) -> bytes:
    return (json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n").encode()


def run_labeling(
    attempts: list[dict],
    *,
    store_root: Path,
    run_id: str,
    store_snapshot: str,
    code_commit: str,
    quarantine_cap: float = 0.10,
    now_utc: str,
) -> LabelRun:
    """attempts: {attempt_id, task_id, raw_output, start}. Byte-deterministic."""
    labels: list[dict] = []
    quarantine: list[dict] = []
    per_source: dict[str, dict[str, int]] = {}
    per_task: dict[str, dict[str, int]] = {}
    for a in sorted(attempts, key=lambda x: x["attempt_id"]):
        outcome = classify_tests_output(a["raw_output"])
        src = a.get("source_class", "?")
        tid = a.get("task_id", "?")
        for bucket in (per_source.setdefault(src, {"n": 0, "q": 0}), per_task.setdefault(tid, {"n": 0, "q": 0})):
            bucket["n"] += 1
        if outcome is None:
            quarantine.append(
                {
                    "attempt_id": a["attempt_id"],
                    "reason_code": "ambiguous_output",
                    "rule_ids": ["R-amb-1"],
                    "trace_ref": "",
                }
            )
            per_source[src]["q"] += 1
            per_task[tid]["q"] += 1
        else:
            labels.append(
                {
                    "attempt_id": a["attempt_id"],
                    "task_id": tid,
                    "outcome": outcome.value,
                    "schema_version": SCHEMA_VERSION,
                    "ruleset_version": RULESET_VERSION,
                }
            )

    total = len(labels) + len(quarantine)
    share = (len(quarantine) / total) if total else 0.0
    if share > quarantine_cap:
        raise QuarantineCapExceeded(f"quarantine share {share:.3f} > cap {quarantine_cap}")

    lb = _labels_bytes(labels)
    qb = _quarantine_bytes(quarantine)
    ruleset_hash = ruleset_content_hash()

    stage = Path(store_root) / ".staging"
    stage.mkdir(parents=True, exist_ok=True)
    labels_file = stage / f"labels-{RULESET_VERSION}.json"
    labels_file.write_bytes(lb)
    q_file = stage / f"quarantine-{RULESET_VERSION}.json"
    q_file.write_bytes(qb)

    inputs = {
        "store_snapshot": store_snapshot,
        "ruleset_version": RULESET_VERSION,
        "ruleset_hash": ruleset_hash,
        "code_commit": code_commit,
        "seeds": {},
        "run_id": run_id,
    }
    try:
        write_artifact("labeling", "labels", f"labels-{ruleset_hash[:12]}", "v0", [labels_file], inputs, Path(store_root))
        write_artifact("labeling", "quarantine", f"quarantine-{ruleset_hash[:12]}", "v0", [q_file], inputs, Path(store_root))
    finally:
        for leftover in stage.glob("*"):
            leftover.unlink()
        stage.rmdir()

    ledger = Path(store_root) / "prereg-ledger.jsonl"
    append_entry(ledger, run_entry(run_id, now_utc, ruleset_hash, store_snapshot))

    summary = {
        "labels": len(labels),
        "quarantined": len(quarantine),
        "quarantine_share": share,
        "quarantine_share_by_source": {
            k: (v["q"] / v["n"] if v["n"] else 0.0) for k, v in per_source.items()
        },
        "quarantine_share_by_task": {
            k: (v["q"] / v["n"] if v["n"] else 0.0) for k, v in per_task.items()
        },
        "ruleset_hash": ruleset_hash,
        "labels_sha256": sha256(lb).hexdigest(),
        "quarantine_sha256": sha256(qb).hexdigest(),
    }
    return LabelRun(labels_file.parent, q_file.parent, summary)


def assert_replay_identical(attempts: list[dict], **kw) -> dict:
    """The determinism hook used by the guard suite: same inputs, two fresh
    stores, byte-identical label AND quarantine payloads."""
    kw = dict(kw)
    root_a = kw.pop("root_a")
    root_b = kw.pop("root_b")
    a = run_labeling(attempts, store_root=Path(root_a), **kw)
    b = run_labeling(attempts, store_root=Path(root_b), **kw)
    assert a.summary["labels_sha256"] == b.summary["labels_sha256"], "labels not byte-identical"
    assert a.summary["quarantine_sha256"] == b.summary["quarantine_sha256"], "quarantine not byte-identical"
    return a.summary
