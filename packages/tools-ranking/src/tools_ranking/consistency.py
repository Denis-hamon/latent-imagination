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
from hashlib import sha256
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
    if not isinstance(pred, dict) or not isinstance(realized, dict):
        raise SchemaError("LI-RANK-003", "predicted/realized must be mappings", {})
    for k, v in pred.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise SchemaError("LI-RANK-003", "predicted score not finite", {"candidate": k})
    for k, v in realized.items():
        if not isinstance(v, bool):
            raise SchemaError("LI-RANK-003", "realized outcome must be a JSON boolean",
                              {"candidate": k, "got": repr(v)[:30]})
    if not all(isinstance(k, str) for k in pred):
        raise SchemaError("LI-RANK-003", "candidate ids must be strings", {})
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
    faulty = 0
    for rec in records:
        if not isinstance(rec, dict):
            raise SchemaError("LI-RANK-003", "evaluation record not a mapping", {})
        for k in ("task_id", "predicted", "realized"):
            if k not in rec:
                raise SchemaError("LI-RANK-003", f"evaluation record missing {k}", {})
        tid = rec["task_id"]
        if not isinstance(tid, str) or not tid:
            raise SchemaError("LI-RANK-003", "task_id must be a non-empty string", {})
        if tid in taus:
            raise SchemaError("LI-RANK-003", "duplicate task_id in the split", {"task_id": tid})
        try:
            t = kendall_tau_b(rec["predicted"], rec["realized"])
        except SchemaError:
            faulty += 1
            taus[tid] = None
            continue
        if t is None:
            degenerate += 1
            taus[tid] = None
        else:
            taus[tid] = t
    defined = [v for v in taus.values() if v is not None]
    return {
        "statistic": "kendall-tau-b",
        "per_task": taus,
        "n_tasks": len(taus),
        "n_degenerate": degenerate,
        "n_faulty_records": faulty,
        "macro_tau": (sum(defined) / len(defined)) if defined else None,
        "degenerate_rule": "all-tied side → undefined, counted, never coerced (consistency-protocol-v1)",
        "fault_policy": "a record failing shape tau-faults into undefined+counted — one bad task never aborts the split",
    }


def heldout_split(candidate_ids: list[str], *, seed: int, hold_frac: float = 0.2,
                  exclude: frozenset[str] = frozenset()) -> list[str]:
    """Deterministic seeded held-out selection; disjoint from `exclude`
    (calibration split) BY CONSTRUCTION — recorded in the manifest."""
    if not candidate_ids:
        raise SchemaError("LI-RANK-003", "no candidates to split", {})
    if not (isinstance(hold_frac, (int, float)) and 0.0 < float(hold_frac) < 1.0):
        raise SchemaError("LI-RANK-003", "hold_frac outside (0,1)", {"got": hold_frac})

    if not isinstance(seed, int) or isinstance(seed, bool):
        raise SchemaError("LI-RANK-003", "seed must be an int (None would seed from OS entropy)", {})
    pool = sorted(set(candidate_ids) - set(exclude))
    if not pool:
        raise SchemaError("LI-RANK-003", "exclusion consumed the pool (disjointness honored)", {})
    # hash-order selection: deterministic ACROSS Python versions (Random.sample
    # has version drift risk — this is a measurement surface)
    from hashlib import sha256 as _sha

    keyed = sorted(pool, key=lambda cid: _sha(f"{seed}:{cid}".encode()).hexdigest())
    n = max(1, round(len(pool) * hold_frac))
    return sorted(keyed[:n])


def publish_consistency_report(
    report: dict, store_root: Path, *, report_version: str,
    dataset_versions: dict[str, str], protocol_sha256: str,
    corpus_version: str, code_commit: str,
    split_manifest_path: Path,
) -> dict:
    """Ship the evaluation as a store artifact (tools-ranking owns
    ranking-reports per AD-4's table extension)."""
    import json
    import tempfile

    from store.emit import compute_store_version, write_artifact

    for name, h in dataset_versions.items():
        if not isinstance(h, str) or len(h) < 8:
            raise SchemaError("LI-RANK-003", "dataset version citation malformed", {"name": name})
    import re as _re

    if not isinstance(protocol_sha256, str) or not _re.fullmatch(r"[0-9a-f]{64}", protocol_sha256):
        raise SchemaError("LI-RANK-003", "protocol citation must be 64-hex lowercase", {})
    if not dataset_versions:
        raise SchemaError("LI-RANK-003", "no dataset versions cited", {})
    sm_sha = sha256(Path(split_manifest_path).read_bytes()).hexdigest() if Path(split_manifest_path).is_file() else None
    if sm_sha is None:
        raise SchemaError("LI-RANK-003", "split manifest missing — the split is not citable", {})
    if report.get("macro_tau") is None:
        raise SchemaError("LI-RANK-004",
                          "all-degenerate split — publish ONLY with a header caveat (protocol v1)",
                          {})
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "consistency-report.json"
        f.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n")
        inputs = {
            "store_snapshot": compute_store_version(store_root),
            "ruleset_version": protocol_sha256,
            "code_commit": code_commit,
            "seeds": {},
            "corpus_version": corpus_version,
            "dataset_versions": dataset_versions,
            "split_manifest_sha256": sm_sha,
        }
        return write_artifact("tools-ranking", "ranking-report", "ordering-consistency",
                              report_version, [f], inputs, store_root).manifest
