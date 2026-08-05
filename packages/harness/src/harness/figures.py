"""Act I figure pipeline — ERBVE curve per (family, generation) with claim/context
separation (FR-6). Figures are derived artifacts with inputs blocks (AD-13),
persisted via the store (publish_figure, harness-owned writer).

JSON figures only in v1: byte-deterministic for Tier-1 replay (review-locked).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import store

from harness.metrics import compute_erbve


@dataclass(frozen=True)
class Taxonomy:
    claim_series: frozenset[tuple[str, str]]  # {(family, generation)}
    context_series: frozenset[tuple[str, str]]

    def is_claim(self, family: str, generation: str) -> bool:
        return (family, generation) in self.claim_series


def load_taxonomy(text: str) -> Taxonomy:
    import tomllib

    data = tomllib.loads(text)
    claim = {(r["family"], r["generation"]) for r in data.get("claim", [])}
    ctx = {(r["family"], r["generation"]) for r in data.get("context", [])}
    return Taxonomy(frozenset(claim), frozenset(ctx))


def erbve_curve(
    labels: list[dict],
    *,
    task_of_attempt,
    start_of_attempt,
    series_of_attempt,  # attempt_id -> (family, generation)
    taxonomy: Taxonomy,
) -> dict[str, Any]:
    """One curve point per series. Claim/context kept strictly apart. The claim
    line IS the pre-registered statistic: macro per task across ALL claim
    tasks (sum of task rates / number of claim tasks) — never a mean of
    family means (C1 fix)."""
    overlap = taxonomy.claim_series & taxonomy.context_series
    if overlap:
        raise ValueError(f"taxonomy conflict: series in BOTH claim and context: {sorted(overlap)}")

    by_series: dict[tuple[str, str], list[dict]] = {}
    for lbl in labels:
        aid = lbl["attempt_id"]
        try:
            series = series_of_attempt(aid)
        except KeyError as e:
            raise ValueError(f"label references unknown attempt for series mapping: {aid}") from e
        by_series.setdefault(series, []).append(lbl)

    points = []
    for (fam, gen), rows in sorted(by_series.items()):
        rep = compute_erbve(rows, task_of_attempt=task_of_attempt, start_of_attempt=start_of_attempt)
        points.append(
            {
                "family": fam,
                "generation": gen,
                "claim": taxonomy.is_claim(fam, gen),
                "macro_rate": rep.macro_rate,
                "micro_rate": rep.micro_rate,
                "total_attempts": rep.total_attempts,
                "total_false_starts": rep.total_false_starts,
                "n_tasks": len(rep.per_task),
            }
        )
    claim_points = [p for p in points if p["claim"]]
    unknown = sorted({(p["family"], p["generation"]) for p in claim_points} - taxonomy.claim_series)
    if unknown:
        raise ValueError(f"claim data in series NOT registered in taxonomy: {unknown}")

    # The registered claim line: pooled macro-per-task over all claim points.
    claim_task_rates: list[float] = []
    for p in claim_points:
        rows = by_series[(p["family"], p["generation"])]
        rep = compute_erbve(rows, task_of_attempt=task_of_attempt, start_of_attempt=start_of_attempt)
        claim_task_rates.extend(t.rate for t in rep.per_task)
    claim_macro = (
        sum(claim_task_rates) / len(claim_task_rates) if claim_task_rates else None
    )
    claim_micro = None
    if claim_points:
        ta = sum(p["total_attempts"] for p in claim_points)
        tf = sum(p["total_false_starts"] for p in claim_points)
        claim_micro = (tf / ta) if ta else None
    return {
        "figure": "erbve_curve_v1",
        "points": points,
        "claim_line": {
            "macro_per_task": claim_macro,
            "micro_pooled": claim_micro,
            "level_note": "macro_per_task is the claim line; pooled micro printed under",
        },
        "context_policy": "context series rendered, never averaged into claim lines",
    }


def headline(figure: dict[str, Any]) -> str:
    """The five-second form (FR-7), derived from the claim line. Refuses to
    issue a claim-shaped sentence on a figure with no claim points."""
    claim_points = [p for p in figure["points"] if p["claim"]]
    if not claim_points:
        raise ValueError("no claim series in this figure — refusing a claim-shaped headline")
    total_a = sum(p["total_attempts"] for p in claim_points)
    total_f = sum(p["total_false_starts"] for p in claim_points)
    return (
        f"{total_f} attempts out of {total_a} failed to pass the task's tests "
        f"before a valid execution ran."
    )


def publish_figure(
    figure: dict[str, Any],
    *,
    store_root: Path,
    figure_id: str,
    figure_version: str,
    inputs: dict[str, Any],
) -> Path:
    """Persist a figure AS a store artifact with its AD-13 inputs block.
    The manifest is what a viewer of the figure resolves store version + query from.
    """
    root = Path(store_root)
    stage = root / ".staging"
    stage.mkdir(parents=True, exist_ok=True)
    f = stage / f"{figure_id}.json"
    f.write_text(json.dumps(figure, indent=2, sort_keys=True) + "\n")
    try:
        return store.write_artifact(
            stage="harness",
            artifact_type="figure",
            artifact_id=figure_id,
            artifact_version=figure_version,
            files=[f],
            inputs=inputs,
            store_root=root,
        ).manifest_path
    finally:
        f.unlink(missing_ok=True)
        if stage.exists() and not any(stage.iterdir()):
            stage.rmdir()
