"""Watermark control matrix: SWE-smith ONLY, both classes, same corpus/models.

Positives = resolved=true agent patches; negatives = resolved=false agent patches.
Same distribution of instances, same models, same task population. If precision
collapses here, the fused-corpus result was a provenance watermark. If it holds,
consequence prediction is learnable from frozen features.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_matched_matrix(
    matched_path: Path,
    smith_tasks_path: Path,
    out_path: Path,
    *,
    max_per_class_per_instance: int = 1,  # one patch per (instance, resolved) — no dup floods
) -> dict[str, Any]:
    matched = json.loads(Path(matched_path).read_text())
    tasks = json.loads(Path(smith_tasks_path).read_text())
    by_id = {t["instance_id"]: t for t in tasks}

    seen: set[tuple[str, bool]] = set()
    rows: list[dict[str, Any]] = []
    joined = 0
    for it in matched:
        key = (it["instance_id"], it["resolved"])
        if key in seen:
            continue
        seen.add(key)
        t = by_id.get(it["instance_id"])
        if not t:
            continue
        joined += 1
        rows.append(
            {
                "instance_id": f"smith::{it['instance_id']}::{it['model']}::{int(it['resolved'])}",
                "repo": t.get("repo", ""),
                "patch": it["patch"],
                "problem_statement": t.get("problem_statement", ""),
                "FAIL_TO_PASS": t.get("FAIL_TO_PASS", []),
                "label": 1 if it["resolved"] else 0,
                "source": "swe-smith-matched",
            }
        )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n")
    manifest = {
        "rows": len(rows),
        "positives": sum(1 for r in rows if r["label"] == 1),
        "negatives": sum(1 for r in rows if r["label"] == 0),
        "joined": joined,
        "repos": len({r["repo"] for r in rows}),
        "rule": "same corpus, same models, one patch per (instance, resolved)",
    }
    (out_path.parent / "matched-matrix-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
