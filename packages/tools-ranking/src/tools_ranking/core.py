"""Candidate ranking core (story 8.1, FR-23): N ≥ 2 patches → total order with
explicit ties.

Doctrine (AD-14 + advisory-scaffold 2026-08-06): scores come ONLY from the
hash-pinned local predictor (gate's pinned snapshot port). Ties are FLAGGED,
never silently coin-flipped: identical scores group into a tie bucket and the
tie displays a deterministic tie-break trace (patch_sha256 ascending, stated).

Determinism contract (AC): same inputs + same model version ⇒ identical
output bytes; a property test shuffles input order and demands byte-equality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core_schema.errors import SchemaError


class Scorer(Protocol):
    def score(self, document: str) -> float: ...


@dataclass(frozen=True)
class Ranked:
    candidate_id: str        # caller-provided label
    patch_sha256: str
    score: float             # flip probability — LOWER ranks first (fewer false starts)
    rank: int                # 1-based; ties share the rank
    tie_group: bool          # True when another candidate shares the score
    tie_break: str | None    # "patch_sha256 ascending" when grouped, else None


def rank_candidates(scorer: Scorer, candidates: list[dict]) -> list[Ranked]:
    """Total order, ties explicit. candidates: [{id, patch_diff}]. ≥2 required."""
    if len(candidates) < 2:
        raise SchemaError("LI-RANK-001", "ranking needs N≥2 candidates", {"got": len(candidates)})
    seen: set[str] = set()
    scored = []
    for c in candidates:
        cid = c.get("id")
        diff = c.get("patch_diff")
        if not isinstance(cid, str) or not cid:
            raise SchemaError("LI-RANK-001", "candidate missing id", {})
        if cid in seen:
            raise SchemaError("LI-RANK-001", "duplicate candidate id", {"id": cid})
        seen.add(cid)
        if not isinstance(diff, str):
            raise SchemaError("LI-RANK-001", "candidate patch_diff must be text", {"id": cid})
        from hashlib import sha256

        sha = sha256(diff.encode()).hexdigest()
        s = scorer.score(diff)
        if not (0.0 <= s <= 1.0):
            raise SchemaError("LI-RANK-001", "scorer returned outside [0,1]", {"id": cid, "got": s})
        scored.append({"id": cid, "sha": sha, "score": s})

    # lower score first; ties broken by patch_sha256 ASCENDING (deterministic)
    scored.sort(key=lambda r: (r["score"], r["sha"]))

    out: list[Ranked] = []
    i = 0
    while i < len(scored):
        j = i
        while j + 1 < len(scored) and scored[j + 1]["score"] == scored[i]["score"]:
            j += 1
        group = scored[i : j + 1]
        grouped = len(group) > 1
        rank_value = i + 1  # standard competition ranking (1,2,2,4)
        for member in group:
            out.append(Ranked(
                candidate_id=member["id"], patch_sha256=member["sha"],
                score=member["score"], rank=rank_value, tie_group=grouped,
                tie_break="patch_sha256 ascending" if grouped else None,
            ))
        i = j + 1
    return out


def serialize_ordering(rows: list[Ranked]) -> str:
    """The AC determinism surface: identical inputs+model ⇒ identical BYTES."""
    import json

    return json.dumps([
        {"candidate_id": r.candidate_id, "patch_sha256": r.patch_sha256, "score": r.score,
         "rank": r.rank, "tie_group": r.tie_group, "tie_break": r.tie_break}
        for r in rows
    ], indent=1, sort_keys=True) + "\n"
