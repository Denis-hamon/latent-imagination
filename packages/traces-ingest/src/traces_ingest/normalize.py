"""Landing → canonical normalizer: sanitize, extract attempts, dedup cross-source."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from core_schema.errors import SchemaError
from core_schema.identity import attempt_id, normalize_diff, task_fingerprint

from traces_ingest.sanitize import sanitize_text

# pre-registered precedence: which source wins a canonical dedup collision
PRECEDENCE = ["own_harbor_run", "public_trajectory_collection", "public_ci_logs"]


@dataclass
class NormalizedAttempt:
    attempt_id: str
    task_id: str
    patch_hash: str
    env_fingerprint: dict[str, Any]
    attempt_window: dict[str, str]
    raw_test_output_ref: str
    provenance: dict[str, Any]
    source_id: str
    source_class: str


@dataclass
class NormalizeReport:
    accepted: list[NormalizedAttempt] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    dedup_collisions: list[dict[str, str]] = field(default_factory=list)


def _attempt_from_record(rec: dict[str, Any]) -> NormalizedAttempt:
    """Construct from a deposit record; raises on missing/invalid fields."""
    required = ["task", "patch_diff", "env_fingerprint", "attempt_start", "raw_test_output_ref"]
    missing = [k for k in required if k not in rec]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    task = rec["task"]
    task_id = task_fingerprint(task["repo_full_name"], task["commit_sha"], task["f2p_tests"])
    start = datetime.fromisoformat(str(rec["attempt_start"]))
    aid = attempt_id(
        task_id,
        rec["patch_diff"],
        _fp_from(rec["env_fingerprint"]),
        start,
    )
    end = datetime.fromisoformat(str(rec.get("attempt_end", rec["attempt_start"])))
    return NormalizedAttempt(
        attempt_id=aid,
        task_id=task_id,
        patch_hash=sha256(normalize_diff(rec["patch_diff"]).encode()).hexdigest(),
        env_fingerprint=rec["env_fingerprint"],
        attempt_window={"start": start.isoformat(), "end": end.isoformat()},
        raw_test_output_ref=rec["raw_test_output_ref"],
        provenance=rec.get("provenance", {}),
        source_id=rec["source_id"],
        source_class=rec["source_class"],
    )


def _fp_from(d: dict[str, Any]):
    from core_schema.domain import EnvironmentFingerprint

    return EnvironmentFingerprint(**d)


def normalize_landing(
    landing_root: Path, precedence: list[str] | None = None
) -> NormalizeReport:
    """Read every deposit record under landing_root, sanitize the raw blob
    reference TEXT (counts to the report), build canonical attempts, dedup."""
    precedence = precedence or PRECEDENCE
    report = NormalizeReport()
    by_id: dict[str, NormalizedAttempt] = {}
    for dep in sorted(Path(landing_root).rglob("*.deposit.json")):
        raw = json.loads(dep.read_text())
        rec = raw.get("record", raw)
        # sanitize the raw test output ref *content path string* only when
        # we own reading it — here we sanitize the RECORD-level text fields.
        safe = sanitize_text(json.dumps(rec.get("provenance", {})))
        if safe.total:
            report.counts["sanitized_keys"] = report.counts.get("sanitized_keys", 0) + safe.total
        try:
            att = _attempt_from_record(rec)
        except (ValueError, KeyError, TypeError, SchemaError) as e:  # malformed data — reject with reason count
            cls = type(e).__name__
            report.rejected.append({"file": dep.name, "error": cls})
            report.counts[f"rejected_{cls}"] = report.counts.get(f"rejected_{cls}", 0) + 1
            continue
        if att.attempt_id in by_id:
            incumbent = by_id[att.attempt_id]
            winner = min((incumbent, att), key=lambda a: precedence.index(a.source_class))
            report.dedup_collisions.append(
                {
                    "attempt_id": att.attempt_id[:12],
                    "kept": winner.source_id,
                    "dropped": (att if winner is incumbent else incumbent).source_id,
                }
            )
            by_id[att.attempt_id] = winner
            report.counts["dedup_dropped"] = report.counts.get("dedup_dropped", 0) + 1
        else:
            by_id[att.attempt_id] = att
    report.accepted = list(by_id.values())
    return report
