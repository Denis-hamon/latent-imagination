"""Tier-2 divergence reporting — the named env-diff (never "didn't match")."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnvDiff:
    python: str
    platform: str
    intent: str = "tier2"  # re-execution tier marker

    def to_dict(self) -> dict[str, str]:
        return {"python": self.python, "platform": self.platform, "intent": self.intent}


@dataclass(frozen=True)
class DivergenceReport:
    claim: str
    published: float
    reproduced: float
    delta_pp: float
    within: bool
    first_diverging_artifact: str | None


def compare_within_tolerance(
    claim: str,
    published: float,
    reproduced: float,
    *,
    tolerance_pp: float = 2.0,
    first_diverging_artifact: str | None = None,
) -> DivergenceReport:
    """±2.0 pp INCLUSIVE. Refuses NaN/Inf and negative tolerances — a comparator
    that prints nonsense is worse than one that refuses."""
    import math

    if not math.isfinite(published) or not math.isfinite(reproduced):
        raise ValueError(f"non-finite comparison input: {published=} {reproduced=}")
    if tolerance_pp < 0:
        raise ValueError(f"negative tolerance {tolerance_pp} is meaningless")
    delta = abs(reproduced - published) * 100.0
    delta_r = round(delta, 4)
    # decide on the ROUNDED display value so report and re-computation agree
    return DivergenceReport(
        claim=claim,
        published=published,
        reproduced=reproduced,
        delta_pp=delta_r,
        within=(delta_r <= tolerance_pp),
        first_diverging_artifact=first_diverging_artifact,
    )
