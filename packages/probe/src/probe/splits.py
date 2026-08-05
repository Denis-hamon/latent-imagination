"""Repo-grouped train/eval splits (mandatory, FR-12).

The split lives in a MANIFEST — every arm reads the same one. Nothing about the
split may vary per arm (UJ-2's sandbag audit).
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any


def repo_grouped_split(
    items: list[dict[str, Any]],
    *,
    eval_frac: float = 0.2,
    seed: int = 20260805,
) -> dict[str, Any]:
    """Split by repo, never by row. A repo's items live in exactly ONE side.

    AMENDED RULE (design.toml [eval_split], 2026-08-05 — recorded before
    training): repos sorted by size desc; every k-th mid-size repo goes to eval
    so the eval set covers ~eval_frac of items, not of repos. Deterministic,
    seed-independent by construction."""
    if not 0 < eval_frac < 1:
        raise ValueError("eval_frac in (0,1)")
    by_repo: dict[str, list[str]] = {}
    for it in items:
        by_repo.setdefault(it.get("repo", ""), []).append(it["instance_id"])
    ordered = sorted(by_repo.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    k = max(2, round(1 / eval_frac))
    eval_repos: set[str] = set()
    eval_items = 0
    target = round(len(items) * eval_frac)
    # walk the size ladder, then step back if we overshoot
    for idx in range(len(ordered)):
        if idx % k != 1:
            continue
        repo, ids = ordered[idx]
        if eval_items + len(ids) > target * 1.5 and eval_repos:
            break
        eval_repos.add(repo)
        eval_items += len(ids)
    if not eval_repos:  # tiny slices: take the second-biggest repo
        eval_repos = {ordered[1][0] if len(ordered) > 1 else ordered[0][0]}
    train = [i for r, ids in by_repo.items() if r not in eval_repos for i in ids]
    eval_ = [i for r in eval_repos for i in by_repo[r]]
    manifest = {
        "seed": "seed-independent",
        "rule": "repo-grouped,size-stratified,k-th-mid-repos",
        "eval_frac_target": eval_frac,
        "eval_items_share": eval_items / len(items) if items else 0,
        "n_repos_eval": len(eval_repos),
        "eval_repos": sorted(eval_repos),
        "train_instance_ids": sorted(train),
        "eval_instance_ids": sorted(eval_),
        "hash": sha256(
            json.dumps({"rule": "repo-grouped,size-stratified", "eval_repos": sorted(eval_repos)}, sort_keys=True).encode()
        ).hexdigest(),
    }
    return manifest


def write_split(manifest: dict[str, Any], out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return out_path
