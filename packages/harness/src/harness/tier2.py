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
    """±2.0 pp INCLUSIVE (OQ-5 answer pre-registered in TIER2.md)."""
    delta = abs(reproduced - published) * 100.0
    # Inclusive boundary with float-noise guard: ±1e-9 pp around the edge.
    return DivergenceReport(
        claim=claim,
        published=published,
        reproduced=reproduced,
        delta_pp=round(delta, 4),
        within=(delta <= tolerance_pp + 1e-9),
        first_diverging_artifact=first_diverging_artifact,
    )
