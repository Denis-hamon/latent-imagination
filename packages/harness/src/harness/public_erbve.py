"""Act I public-trajectory measurement: ERBVE over real SWE-smith runs.

NOT the pre-registered claim-point protocol (that's the campaign machinery;
this is the published public-data curve — same metric, honest provenance, and
the registry will carry the coverage disclosure). Each trajectory row becomes
one Execution Attempt (resolved=true ↔ VALID_EXECUTION, resolved=false ↔
FALSE_START); attempt_window is fabricated from the trajectory (one row per
run — generation buckets are the model families). Judge-free by construction:
labels ARE the published `resolved` flags, computed upstream by repo tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from core_schema.domain import LabelOutcome
from harness.metrics import compute_erbve

MODEL_TO_FAMILY = {
    "claude-3-5-sonnet-20241022": ("claude", "2024"),
    "claude-3-7-sonnet-20250219": ("claude", "2025"),
    "gpt-4o-2024-08-06": ("openai", "2024"),
}


def measure_public_erbve(raw_parquet: Path) -> dict:
    """Aggregate ERBVE per (family, generation) from SWE-smith trajectories."""
    rows = duckdb.sql(
        f"""select instance_id, model, resolved from read_parquet('{raw_parquet}')"""
    ).fetchall()

    # every trajectory row = one attempt; nothing more, nothing less
    labels: list[dict] = []
    task_of: dict[str, str] = {}
    start_of: dict[str, str] = {}
    series_of: dict[str, tuple[str, str]] = {}
    base = "2026-01-01T00:00:00Z"
    for i, (iid, model, resolved) in enumerate(rows):
        aid = f"{iid}::{model}::{i}"
        outcome = (
            LabelOutcome.VALID_EXECUTION if resolved else LabelOutcome.FALSE_START_TESTS_RAN_NO_FLIP
        )
        labels.append({"attempt_id": aid, "outcome": outcome.value})
        task_of[aid] = iid
        start_of[aid] = f"2026-01-01T{(i % 86400) // 3600:02d}:{(i % 3600) // 60:02d}:00Z"
        series_of[aid] = MODEL_TO_FAMILY.get(model, ("unknown", "unknown"))

    from harness.figures import Taxonomy, erbve_curve, headline

    claim_pairs = {v for v in series_of.values()}
    taxonomy = Taxonomy(
        claim_series=frozenset(claim_pairs),
        context_series=frozenset(),
    )
    fig = erbve_curve(
        labels,
        task_of_attempt=lambda a: task_of[a],
        start_of_attempt=lambda a: start_of[a],
        series_of_attempt=lambda a: series_of[a],
        taxonomy=taxonomy,
    )
    return {"figure": fig, "headline": headline(fig), "n_attempts": len(labels)}


def main() -> int:
    import sys

    parquet = sys.argv[1]
    out_path = Path(sys.argv[2] if len(sys.argv) > 2 else "governance/public-measurement-2026-08-06.json")
    res = measure_public_erbve(Path(parquet))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2, default=str) + "\n")
    print(json.dumps({"n_attempts": res["n_attempts"], "headline": res["headline"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
