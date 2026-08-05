"""Act I figure pipeline — ERBVE curve per (family, generation) with claim/context
separation (FR-6). Figures are derived artifacts with inputs blocks (AD-13).

JSON figures only in v1: byte-deterministic for Tier-1 replay (review-locked).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    """Compute one curve point per series. Claim/context are kept strictly apart:
    context points are rendered but never averaged into the claim line."""
    by_series: dict[tuple[str, str], list[dict]] = {}
    for lbl in labels:
        by_series.setdefault(series_of_attempt(lbl["attempt_id"]), []).append(lbl)

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
    claim_macro = (
        sum(p["macro_rate"] for p in claim_points) / len(claim_points) if claim_points else None
    )
    claim_micro = None
    if claim_points:
        ta = sum(p["total_attempts"] for p in claim_points)
        tf = sum(p["total_false_starts"] for p in claim_points)
        claim_micro = (tf / ta) if ta else None
    return {
        "figure": "erbve_curve_v1",
        "points": points,
        "claim_line": {"macro_rate": claim_macro, "micro_rate": claim_micro},
        "context_policy": "context series rendered, never averaged into claim lines",
    }


def headline(figure: dict[str, Any]) -> str:
    """The five-second form (FR-7)."""
    total_a = sum(p["total_attempts"] for p in figure["points"] if p["claim"])
    total_f = sum(p["total_false_starts"] for p in figure["points"] if p["claim"])
    return (
        f"{total_f} attempts out of {total_a} failed to pass the task's tests "
        f"before a valid execution ran."
    )
