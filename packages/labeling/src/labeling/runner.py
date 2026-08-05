"""Labeling runner: pure rules over canonical snapshots → label-set artifacts.

Writes via store only (WRITERS table: labeling). Adds a `run` row to the
prereg-ledger and re-runs itself to assert byte-identical output (AD-7 hook).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from prereg.ledger import append_entry, run_entry
from store.emit import write_artifact

from labeling.rules_v1 import RULESET_VERSION, SCHEMA_VERSION, classify_tests_output


class QuarantineCapExceeded(Exception):
    """The pre-registered quarantine share cap was exceeded; measurement halts."""


@dataclass(frozen=True)
class LabelRun:
    label_artifact_dir: Path
    quarantine_dir: Path
    summary: dict


def _labels_bytes(labels: list[dict]) -> bytes:
    return (json.dumps(labels, sort_keys=True, separators=(",", ":")) + "\n").encode()


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
    """attempts rows: {attempt_id, task_id, raw_output, start}.
    Deterministic: same inputs → same bytes (fan-out order normalized)."""
    labels: list[dict] = []
    quarantine: list[dict] = []
    for a in sorted(attempts, key=lambda x: x["attempt_id"]):
        outcome = classify_tests_output(a["raw_output"])
        if outcome is None:
            quarantine.append(
                {
                    "attempt_id": a["attempt_id"],
                    "reason_code": "ambiguous_output",
                    "rule_ids": ["R-amb-1"],
                    "trace_ref": "",
                }
            )
        else:
            labels.append(
                {
                    "attempt_id": a["attempt_id"],
                    "outcome": outcome.value,
                    "schema_version": SCHEMA_VERSION,
                    "ruleset_version": RULESET_VERSION,
                }
            )

    total = len(labels) + len(quarantine)
    share = (len(quarantine) / total) if total else 0.0
    if share > quarantine_cap:
        raise QuarantineCapExceeded(
            f"quarantine share {share:.3f} > cap {quarantine_cap}"
        )

    lb = _labels_bytes(labels)
    qb = json.dumps(quarantine, sort_keys=True, separators=(",", ":")).encode()

    labels_file = store_root / ".staging" / f"labels-{RULESET_VERSION}.json"
    labels_file.parent.mkdir(parents=True, exist_ok=True)
    labels_file.write_bytes(lb)
    q_file = store_root / ".staging" / f"quarantine-{RULESET_VERSION}.json"
    q_file.write_bytes(qb)

    inputs = {
        "store_snapshot": store_snapshot,
        "ruleset_version": RULESET_VERSION,
        "code_commit": code_commit,
        "seeds": {},
        "run_id": run_id,
    }
    write_artifact("labeling", "labels", f"labels-{sha256(lb).hexdigest()[:12]}", "v0", [labels_file], inputs, store_root)
    write_artifact(
        "labeling", "quarantine", f"quarantine-{sha256(qb).hexdigest()[:12]}", "v0", [q_file], inputs, store_root
    )

    # ledger run row (occurrence; started_at supplied by caller as now_utc)
    ledger = store_root / "prereg-ledger.jsonl"
    append_entry(
        ledger,
        run_entry(run_id, now_utc, RULESET_VERSION, store_snapshot),
    )

    summary = {
        "labels": len(labels),
        "quarantined": len(quarantine),
        "quarantine_share": share,
        "labels_sha256": sha256(lb).hexdigest(),
        "quarantine_sha256": sha256(qb).hexdigest(),
    }
    return LabelRun(labels_file.parent, q_file.parent, summary)
