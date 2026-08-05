"""Landing → canonical normalizer: sanitize, extract attempts, dedup cross-source.

Contract:
- provenance text is sanitized BEFORE storage; the stored record carries the
  REDACTED text plus ``sanitized: true`` when any class hit (disclosed, not silent)
- unknown ``source_class`` values are rejected+counted like any malformed field
- identical logical attempts collapse by canonical identity (attempt_id); the
  precedence table is data-driven (PRECEDENCE list), kept in one place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    sanitized: bool = False


@dataclass
class NormalizeReport:
    accepted: list[NormalizedAttempt] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    dedup_collisions: list[dict[str, str]] = field(default_factory=list)


def _reject(report: NormalizeReport, dep: Path, cls: str) -> None:
    report.rejected.append({"file": dep.name, "error": cls})
    report.counts[f"rejected_{cls}"] = report.counts.get(f"rejected_{cls}", 0) + 1


def _attempt_from_record(rec: dict[str, Any], sanitized_provenance: dict[str, Any], sanitized: bool) -> NormalizedAttempt:
    """Construct from a deposit record; raises on missing/invalid fields."""
    required = ["task", "patch_diff", "env_fingerprint", "attempt_start", "raw_test_output_ref"]
    missing = [k for k in required if k not in rec]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    source_class = rec.get("source_class", "")
    if source_class not in PRECEDENCE:
        raise ValueError(f"unknown source_class: {source_class!r}")
    task = rec["task"]
    task_id = task_fingerprint(task["repo_full_name"], task["commit_sha"], task["f2p_tests"])
    start_raw = datetime.fromisoformat(str(rec["attempt_start"]))
    # normalize to UTC at the boundary: canonical bytes must not depend on offsets
    start = _aware_or_raise(start_raw).astimezone(UTC)
    end = _aware_or_raise(
        datetime.fromisoformat(str(rec.get("attempt_end", rec["attempt_start"])))
    ).astimezone(UTC)
    aid = attempt_id(
        task_id,
        rec["patch_diff"],
        _fp_from(rec["env_fingerprint"]),
        start_raw,
    )
    return NormalizedAttempt(
        attempt_id=aid,
        task_id=task_id,
        patch_hash=sha256(normalize_diff(rec["patch_diff"]).encode()).hexdigest(),
        env_fingerprint=rec["env_fingerprint"],
        attempt_window={"start": _utc_z(start), "end": _utc_z(end)},
        raw_test_output_ref=rec["raw_test_output_ref"],
        provenance=sanitized_provenance,
        source_id=rec["source_id"],
        source_class=source_class,
        sanitized=sanitized,
    )


def _aware_or_raise(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise SchemaError("LI-CI-002", "naive attempt timestamp", {"value": dt.isoformat()})
    return dt


def _utc_z(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _fp_from(d: dict[str, Any]):
    from core_schema.domain import EnvironmentFingerprint

    return EnvironmentFingerprint(**d)


def normalize_landing(
    landing_root: Path, precedence: list[str] | None = None
) -> NormalizeReport:
    """Read every deposit record under landing_root, sanitize the provenance
    text, build canonical attempts, dedup by canonical identity."""
    precedence = precedence or PRECEDENCE
    report = NormalizeReport()
    by_id: dict[str, NormalizedAttempt] = {}
    for dep in sorted(Path(landing_root).rglob("*.deposit.json")):
        raw = json.loads(dep.read_text())
        rec = raw.get("record", raw)
        prov = rec.get("provenance", {})
        prov_text = json.dumps(prov, sort_keys=True) if prov else ""

        # Sanitize RAW provenance values (not the serialized dump).
        safe_prov: dict[str, Any] = {}
        total_hits = 0
        for k, v in prov.items():
            if isinstance(v, str):
                res = sanitize_text(v)
                safe_prov[k] = res.text
                total_hits += res.total
                for cls, n in res.counts.items():
                    report.counts[f"sanitized_{cls}"] = report.counts.get(f"sanitized_{cls}", 0) + n
            else:
                safe_prov[k] = v
        if total_hits:
            report.counts["sanitized_records"] = report.counts.get("sanitized_records", 0) + 1
        _ = prov_text  # serialized form never sanitized — see policy note (raw-text rule)

        try:
            att = _attempt_from_record(rec, safe_prov, bool(total_hits))
        except (ValueError, KeyError, TypeError, SchemaError) as e:
            _reject(report, dep, type(e).__name__)
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


def write_canonical_snapshot(
    report: NormalizeReport,
    store_root: Path,
    *,
    store_snapshot: str,
    code_commit: str,
    artifact_id: str,
) -> Path:
    """Emit the accepted attempts as a canonical snapshot (jsonl bytes),
    write through the store helper only, and re-validate the store inline."""
    import store

    rows = [
        {
            "attempt_id": a.attempt_id,
            "task_id": a.task_id,
            "patch_sha256": a.patch_hash,
            "env_fingerprint": a.env_fingerprint,
            "attempt_start": a.attempt_window["start"],
            "attempt_end": a.attempt_window["end"],
            "raw_test_output_ref": a.raw_test_output_ref,
            "provenance": a.provenance,
            "source_id": a.source_id,
            "source_class": a.source_class,
            "sanitized": a.sanitized,
        }
        for a in sorted(report.accepted, key=lambda x: x.attempt_id)
    ]
    blob = (json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n").encode()

    stage = store_root / ".staging"
    stage.mkdir(parents=True, exist_ok=True)
    snap_file = stage / f"snapshot-{artifact_id}.json"
    snap_file.write_bytes(blob)

    inputs = {
        "store_snapshot": store_snapshot,
        "ruleset_version": "",
        "code_commit": code_commit,
        "seeds": {},
    }
    out = store.write_artifact(
        stage="traces-ingest",
        artifact_type="canonical-snapshot",
        artifact_id=artifact_id,
        artifact_version="v0",
        files=[snap_file],
        inputs=inputs,
        store_root=store_root,
    )
    report_validation = store.validate_store(store_root)  # type: ignore[attr-defined]
    if not report_validation.ok:
        raise RuntimeError(
            f"store failed validation right after ingest write: {report_validation.errors}"
        )
    # staging is transient: clean it after the committed write
    for leftover in stage.glob("*"):
        leftover.unlink()
    stage.rmdir()
    return out.manifest_path
