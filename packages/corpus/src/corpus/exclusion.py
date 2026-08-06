"""Versioned exclusion rule + leakage audit (story 4.2, FR-15/R11).

An item COLLIDES when its repo is a constituent repo (conservative — a
memorized repo voids arbitration even across commits), or its instance/PR key
is declared. The audit is written INTO the emitted artifact; a kept collision
fails the build (LI-CORPUS-006) — the check, not the intention, is enforced.
"""

from __future__ import annotations

import tomllib
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError
from pydantic import BaseModel, ConfigDict

from corpus.constituents import repo_set
from corpus.noisy import NoisyItem


class ExclusionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    constituents_file: str
    constituents_sha256: str
    strategy: str


def load_rule(path: Path) -> ExclusionRule:
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
    actual = sha256(Path(rule.constituents_file).read_bytes()).hexdigest()
    if actual != rule.constituents_sha256:
        raise SchemaError(
            "LI-CORPUS-007",
            "rule cites a constituents hash that does not match the file — stale rule",
            {"cited": rule.constituents_sha256, "actual": actual},
        )
    return rule


def apply_exclusion(
    items: list[NoisyItem], constituents: dict
) -> tuple[list[NoisyItem], list[dict], dict]:
    """Conservative filter: repo-level collision excludes even across commits."""
    repos = repo_set(constituents)
    kept: list[NoisyItem] = []
    excluded: list[dict] = []
    for item in items:
        if item.repo in repos:
            excluded.append({"item_id": item.item_id, "reason": "repo", "repo": item.repo})
        else:
            kept.append(item)
    by_reason: dict[str, int] = {}
    for e in excluded:
        by_reason[e["reason"]] = by_reason.get(e["reason"], 0) + 1
    audit = {
        "kept": len(kept),
        "excluded": len(excluded),
        "by_reason": by_reason,
        "examples": [e["item_id"] for e in excluded[:5]],
        "zero_overlap": not any(
            item.repo in repos for item in kept
        ),
        "constituents": {"instance_ids": len(constituents["instance_ids"]),
                          "repos": len(constituents["repos"])},
    }
    return kept, excluded, audit


def assert_no_overlap(items: list[NoisyItem], constituents: dict) -> None:
    """The AC-2 build check: any collision RAISES (LI-CORPUS-006)."""
    repos = repo_set(constituents)
    hits = [i for i in items if i.repo in repos]
    if hits:
        raise SchemaError(
            "LI-CORPUS-006",
            "leakage: items collide with eval constituents — build refused",
            {"collisions": len(hits), "example": hits[0].item_id},
        )
