"""Versioned exclusion rule + leakage audit (story 4.2, FR-15/R11).

ONE cited artifact, verified, applied (CR 4.2): `load_rule` resolves the
rule's `constituents_file` relative to the REPO ROOT (the rule lives in
governance/corpus/), hashes it, and RETURNS the loaded constituents — the
caller never picks a second file. Collision legs (audited buckets):
- repo-level (conservative — a memorized repo voids arbitration even across
  commits; comparisons case-folded, GitHub names are case-insensitive);
- pr-level (item's (repo, pr_number) against declared PR keys);
- the instance leg does not apply by construction: noisy items carry no task
  instance ids (the Noisy Tier is task-less) — documented, not faked.

The AC-2 build check re-loads constituents FRESH from the cited file before
asserting — an in-memory aliasing bug in the filter cannot hide a collision.
"""

from __future__ import annotations

import tomllib
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError
from pydantic import BaseModel, ConfigDict

from corpus.constituents import load_constituents, norm_repo, pr_keys, repo_set
from corpus.noisy import NoisyItem


class ExclusionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    constituents_file: str
    constituents_sha256: str
    strategy: str


def _repo_root_for(rule_path: Path) -> Path:
    parts = Path(rule_path).resolve().parents
    # governance/corpus/<rule> → repo root two levels above corpus/
    if len(parts) >= 3 and parts[0].name == "corpus" and parts[1].name == "governance":
        return parts[2]
    raise SchemaError(
        "LI-CORPUS-007", "exclusion rule must live under governance/corpus/",
        {"path": str(rule_path)},
    )


def load_rule(path: Path) -> tuple[ExclusionRule, dict, Path]:
    """Load + verify + BIND. Returns (rule, constituents, constituents_path).

    The cited constituents file is resolved against the repo root (never CWD)
    and its sha256 must equal the citation — stale rules refuse to load."""
    p = Path(path)
    try:
        raw = tomllib.loads(p.read_bytes().decode("utf-8"))
    except FileNotFoundError as exc:
        raise SchemaError("LI-CORPUS-007", "exclusion rule missing", {"path": str(path)}) from exc
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-CORPUS-007", "exclusion rule unparseable", {"path": str(path)}) from exc
    table = raw.get("rule")
    if not isinstance(table, dict):
        raise SchemaError("LI-CORPUS-007", "exclusion rule missing [rule] table", {})
    try:
        rule = ExclusionRule.model_validate(table)
    except ValueError as exc:
        raise SchemaError("LI-CORPUS-007", "exclusion rule invalid", {"err": str(exc)}) from exc
    cpath = _repo_root_for(p) / rule.constituents_file
    try:
        actual = sha256(cpath.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise SchemaError("LI-CORPUS-007", "rule cites a missing constituents file",
                          {"path": str(cpath)}) from exc
    except OSError as exc:
        raise SchemaError("LI-CORPUS-007", "rule constituents unreadable",
                          {"path": str(cpath), "err": str(exc)}) from exc
    if actual != rule.constituents_sha256:
        raise SchemaError(
            "LI-CORPUS-007",
            "rule cites a constituents hash that does not match the file — stale rule",
            {"cited": rule.constituents_sha256, "actual": actual},
        )
    return rule, load_constituents(cpath), cpath


def apply_exclusion(
    items: list[NoisyItem], constituents: dict
) -> tuple[list[NoisyItem], list[dict], dict]:
    """Conservative filter: repo-level + pr-level collision legs."""
    repos = repo_set(constituents)
    prs = pr_keys(constituents)
    kept: list[NoisyItem] = []
    excluded: list[dict] = []
    for item in items:
        pr_key = f"{norm_repo(item.repo)}#{item.pr_number}" if item.pr_number else None
        if norm_repo(item.repo) in repos:
            excluded.append({"item_id": item.item_id, "reason": "repo", "repo": item.repo})
        elif pr_key is not None and pr_key in prs:
            excluded.append({"item_id": item.item_id, "reason": "pr", "repo": item.repo})
        else:
            kept.append(item)
    by_reason: dict[str, int] = {}
    for e in excluded:
        by_reason[e["reason"]] = by_reason.get(e["reason"], 0) + 1
    audit = {
        "kept": len(kept),
        "excluded": len(excluded),
        "by_reason": {"repo": by_reason.get("repo", 0), "pr": by_reason.get("pr", 0)},
        "examples": [{"item_id": e["item_id"], "reason": e["reason"]} for e in excluded[:5]],
        "constituents": {"instance_ids": len(constituents["instance_ids"]),
                          "repos": len(constituents["repos"])},
    }
    return kept, excluded, audit


def assert_no_overlap_cited(items: list[NoisyItem], constituents_path: Path) -> dict:
    """AC-2 build check, non-tautological (CR 4.2): re-load the cited set FRESH
    and test kept items against the independent read. Raises LI-CORPUS-006.
    Returns {zero_overlap} for the audit."""
    fresh = load_constituents(Path(constituents_path))
    repos = repo_set(fresh)
    prs = pr_keys(fresh)
    def _hits(i: NoisyItem) -> bool:
        if norm_repo(i.repo) in repos:
            return True
        pr_key = f"{norm_repo(i.repo)}#{i.pr_number}" if i.pr_number else None
        return pr_key is not None and pr_key in prs

    hits = [i for i in items if _hits(i)]
    if hits:
        raise SchemaError(
            "LI-CORPUS-006",
            "leakage: kept items collide with eval constituents — build refused",
            {"collisions": len(hits), "example": hits[0].item_id},
        )
    return {"zero_overlap": True}
