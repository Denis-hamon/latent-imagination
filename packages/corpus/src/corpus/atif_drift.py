"""ATIF drift watch (story 4.1, AC 2) — runs within ingestion review.

The pin is a Literal in core_schema.trace.ExecutionTrace.schema_version:
ingest REJECTS other versions, so drift would otherwise surface only as
unexplained rejection buckets. The watch instead surveys raw landing deposits
— including the rejected ones — and REPORTS every schema_version seen vs the
expected pin: an upstream format move becomes information, not silence
(addendum §E.4 note 3: ATIF = alignment, not pin; drift is owned here).

Report = occurrence metadata; no network, no store write (AD-6, AD-4).

Invocation (ingestion review wiring, AC2): `python -m corpus.atif_drift
<landing_root>` writes the report as an occurrence artifact under
`<landing_root>/_reviews/atif-drift-report.json` (wall clock allowed, AD-7).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_NON_TRAJECTORY = frozenset({".landing-manifest.json", ".harvest-manifest.json", ".cursor.json", "provenance.json"})


class DriftReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected: str
    scanned: int
    matched: int
    observed: dict[str, int]
    unparseable: int
    drift: bool


def watch(landing_root: Path, expected_version: str) -> DriftReport:
    observed: Counter[str] = Counter()
    scanned = matched = unparseable = 0
    root = Path(landing_root)
    for f in sorted(root.rglob("*.json")) if root.is_dir() else []:
        if f.name in _NON_TRAJECTORY or f.name.endswith(".cursor.json.tmp"):
            continue
        try:
            raw = json.loads(f.read_text(errors="replace"))
        except ValueError:
            unparseable += 1
            continue
        if not isinstance(raw, dict) or "schema_version" not in raw:
            continue  # not a trajectory deposit (e.g. cursor-adjacent files)
        scanned += 1
        version = str(raw["schema_version"])
        observed[version] += 1
        if version == expected_version:
            matched += 1
    return DriftReport(
        expected=expected_version,
        scanned=scanned,
        matched=matched,
        observed=dict(observed),
        unparseable=unparseable,
        drift=any(v != expected_version for v in observed),
    )


def write_report(landing_root: Path, expected_version: str) -> Path:
    """The ingestion-review wiring (AC2, review P7): persist the report as an
    occurrence artifact under the landing zone it just surveyed."""
    import os
    import time

    root = Path(landing_root)
    report = watch(root, expected_version)
    out_dir = root / "_reviews"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump()
    payload["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out = out_dir / "atif-drift-report.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, out)
    return out


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m corpus.atif_drift <landing_root> [expected_version]")
        raise SystemExit(2)
    from corpus.policy import load_policy

    root = Path(sys.argv[1])
    expected = (
        sys.argv[2]
        if len(sys.argv) > 2
        else load_policy(root.parents[0] / "governance" / "corpus" / "harvest-policy-v1.toml")
        .drift_watch.expected_atif_version
    )
    print(write_report(root, expected))
