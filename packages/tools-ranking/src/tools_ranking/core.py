"""Candidate ranking core (story 8.1 + CR, FR-23): N≥2 patches → total order.

Scores come ONLY from the pinned gate predictor line (Scorer protocol —
advisory posture 2026-08-06: the project's "certified" reads "pin-obligatory"
while no arm crosses the bar; see stories 5-1/6-1).

Determinism is TOTAL: identical input SET + same model ⇒ byte-identical output,
even with duplicate patch CONTENT (the tie-break chain is
score → patch_sha256 → candidate_id, all deterministic).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from core_schema.errors import SchemaError


class Scorer(Protocol):
    def score(self, document: str) -> float: ...


@dataclass(frozen=True)
class Ranked:
    candidate_id: str
    patch_sha256: str
    score: float             # flip probability — LOWER ranks first
    rank: int                # competition ranking (1,2,2,4)
    tie_group: bool
    tie_break: str | None    # the named deterministic chain when grouped


TIE_BREAK_NAME = "score, then content sha256, then candidate id"


def rank_candidates(scorer: Scorer, candidates: list[dict]) -> list[Ranked]:
    """Total order with explicit ties. candidates: [{id, patch_diff}]. ≥2."""
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise SchemaError("LI-RANK-001", "ranking needs a list of N≥2 candidates",
                          {"got": len(candidates) if isinstance(candidates, list) else type(candidates).__name__})
    seen: set[str] = set()
    scored = []
    for c in candidates:
        if not isinstance(c, dict):
            raise SchemaError("LI-RANK-001", "candidate must be a mapping", {"got": type(c).__name__})
        cid = c.get("id")
        diff = c.get("patch_diff")
        if not isinstance(cid, str) or not cid:
            raise SchemaError("LI-RANK-001", "candidate missing id", {})
        if cid in seen:
            raise SchemaError("LI-RANK-001", "duplicate candidate id", {"id": cid})
        seen.add(cid)
        if not isinstance(diff, str):
            raise SchemaError("LI-RANK-001", "candidate patch_diff must be text", {"id": cid})
        if not diff.strip():
            raise SchemaError("LI-RANK-001", "empty candidate patch", {"id": cid})
        try:
            sha = sha256(diff.encode("utf-8")).hexdigest()
        except UnicodeEncodeError as exc:
            raise SchemaError("LI-RANK-001", "patch not utf-8 encodable", {"id": cid}) from exc
        try:
            s = scorer.score(diff)
        except SchemaError:
            raise
        except Exception as exc:
            raise SchemaError("LI-RANK-001", "scorer raised mid-ranking",
                              {"id": cid, "err": type(exc).__name__}) from exc
        if isinstance(s, bool) or not isinstance(s, (int, float)) or not math.isfinite(float(s)):
            raise SchemaError("LI-RANK-001", "scorer returned a non-number/out-of-bounds value",
                              {"id": cid, "got": repr(s)[:40]})
        s = float(s)
        if not (0.0 <= s <= 1.0):
            raise SchemaError("LI-RANK-001", "score outside [0,1]", {"id": cid, "got": s})
        scored.append({"id": cid, "sha": sha, "score": s})

    # deterministic, TOTAL: score → content sha → id (every key unique by guards)
    scored.sort(key=lambda r: (r["score"], r["sha"], r["id"]))

    out: list[Ranked] = []
    i = 0
    while i < len(scored):
        j = i
        while j + 1 < len(scored) and scored[j + 1]["score"] == scored[i]["score"]:
            j += 1
        group = scored[i : j + 1]
        grouped = len(group) > 1
        rank_value = i + 1
        for member in group:
            out.append(Ranked(
                candidate_id=member["id"], patch_sha256=member["sha"], score=member["score"],
                rank=rank_value, tie_group=grouped, tie_break=TIE_BREAK_NAME if grouped else None,
            ))
        i = j + 1
    return out


def serialize_ordering(rows: list[Ranked]) -> str:
    """AC determinism surface: identical set + model ⇒ identical bytes."""
    return json.dumps([
        {"candidate_id": r.candidate_id, "patch_sha256": r.patch_sha256, "score": r.score,
         "rank": r.rank, "tie_group": r.tie_group, "tie_break": r.tie_break}
        for r in rows
    ], indent=1, sort_keys=True, allow_nan=False) + "\n"
