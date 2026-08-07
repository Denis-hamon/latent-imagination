"""Ordering-consistency evaluation (story 8.3, FR-24): Kendall's tau-b on a
held-out split, protocol pre-registered, degenerate rule named.

Statistic (registered, `governance/ranking/consistency-protocol-v1.toml`):
Kendall tau-b per task over candidates (predicted score order vs realized
validity order, validity-first), aggregated macro over tasks. Degenerate
rule: a side with ALL candidates tied makes tau-b undefined for that task —
recorded as `undefined (<side>-all-tied)`, COUNTED, never coerced to ±1.
A split whose every task is degenerate is published sub-floor WITH the caveat.
"""

from __future__ import annotations

import math
from pathlib import Path

from core_schema.errors import SchemaError


def kendall_tau_b(pred: dict[str, float], realized: dict[str, bool]) -> float | None:
    """Pairwise tau-b between predicted scores (ascending=better) and realized
    validity (True=patch flips F2P = good candidate). None when degenerate.

    Textbook tau-b: n0 = all pairs; ties per side counted separately;
    denom = sqrt((n0 − t_pred) · (n0 − t_real)); zero denom → degenerate."""
    if set(pred) != set(realized):
        raise SchemaError("LI-RANK-003", "predicted/realized candidate sets differ",
                          {"only_pred": sorted(set(pred) - set(realized)),
                           "only_real": sorted(set(realized) - set(pred))})
    items = sorted(set(pred))
    if len(items) < 2:
        raise SchemaError("LI-RANK-003", "tau needs ≥2 candidates", {"n": len(items)})
    concordant = n0 = 0
    ties_pred = ties_real = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            p_eq = pred[a] == pred[b]
            r_eq = realized[a] == realized[b]
            n0 += 1
            if p_eq:
                ties_pred += 1
            if r_eq:
                ties_real += 1
            if not p_eq and not r_eq:
                p_cmp = (pred[a] > pred[b]) - (pred[a] < pred[b])
                r_cmp = (realized[a] < realized[b]) - (realized[a] > realized[b])  # ascending=better both sides
                concordant += p_cmp * r_cmp  # +1 concordant, −1 discordant
    # NOTE on the second comparison: predicted ascending (low score = good) and
    # realized True-first (True = good) — realized True means SMALLER rank. The
    # comparator r_cmp is (realized[a] < realized[b]) - (realized[a] > realized[b]):
    # True(1) < False(0) → +1 ⇔ a is better than b when only a is valid.
    denom2 = (n0 - ties_pred) * (n0 - ties_real)
    if denom2 <= 0:
        return None  # degenerate: one side fully tied — the registered rule
    return concordant / math.sqrt(denom2)


def evaluate_split(records: list[dict]) -> dict:
    """records: [{task_id, predicted: {cand: score}, realized: {cand: valid: bool}}]
    Returns per-task taus + macro mean over DEFINED tasks + degenerate counts."""
    if not records:
        raise SchemaError("LI-RANK-003", "empty evaluation split", {})
    taus: dict[str, float | None] = {}
    degenerate = 0
    for rec in records:
        for k in ("task_id", "predicted", "realized"):
            if k not in rec:
                raise SchemaError("LI-RANK-003", f"evaluation record missing {k}", {})
        t = kendall_tau_b(rec["predicted"], rec["realized"])
        if t is None:
            degenerate += 1
            taus[rec["task_id"]] = None
        else:
            taus[rec["task_id"]] = t
    defined = [v for v in taus.values() if v is not None]
    return {
        "statistic": "kendall-tau-b",
        "per_task": taus,
        "n_tasks": len(taus),
        "n_degenerate": degenerate,
        "macro_tau": (sum(defined) / len(defined)) if defined else None,  # None = all-degenerate → publish with caveat
        "degenerate_rule": "all-tied side → undefined, counted, never coerced (consistency-protocol-v1)",
    }


def heldout_split(candidate_ids: list[str], *, seed: int, hold_frac: float = 0.2,
                  exclude: frozenset[str] = frozenset()) -> list[str]:
    """Deterministic seeded held-out selection; disjoint from `exclude`
    (calibration split) BY CONSTRUCTION — recorded in the manifest."""
    if not candidate_ids:
        raise SchemaError("LI-RANK-003", "no candidates to split", {})
    if not (0.0 < hold_frac < 1.0):
        raise SchemaError("LI-RANK-003", "hold_frac outside (0,1)", {"got": hold_frac})
    import random

    pool = sorted(set(candidate_ids) - set(exclude))
    if not pool:
        raise SchemaError("LI-RANK-003", "exclusion consumed the pool (disjointness honored)", {})
    n = max(1, int(len(pool) * hold_frac))
    return sorted(random.Random(seed).sample(pool, n))


def publish_consistency_report(
    report: dict, store_root: Path, *, report_version: str,
    dataset_versions: dict[str, str], protocol_sha256: str,
    corpus_version: str, code_commit: str,
) -> dict:
    """Ship the evaluation as a store artifact (tools-ranking owns
    ranking-reports per AD-4's table extension)."""
    import json
    import tempfile

    from store.emit import compute_store_version, write_artifact

    for name, h in dataset_versions.items():
        if not isinstance(h, str) or len(h) < 8:
            raise SchemaError("LI-RANK-003", "dataset version citation malformed", {"name": name})
    if len(protocol_sha256) != 64:
        raise SchemaError("LI-RANK-003", "protocol citation must be 64-hex", {})
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "consistency-report.json"
        f.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        inputs = {
            "store_snapshot": compute_store_version(store_root),
            "ruleset_version": protocol_sha256,
            "code_commit": code_commit,
            "seeds": {},
            "corpus_version": corpus_version,
            "dataset_versions": dataset_versions,
        }
        return write_artifact("tools-ranking", "ranking-report", "ordering-consistency",
                              report_version, [f], inputs, store_root).manifest
