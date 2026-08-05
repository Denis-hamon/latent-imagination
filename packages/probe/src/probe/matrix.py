"""Build the arbitration matrix: Verified gold positives + SWE-smith real negatives.

Registered rule (design.toml amendment): positives = gold patches of kept
Verified instances; negatives = real agent failed patches (resolved=false);
both flow through the SAME renderer and the SAME repo-grouped split.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

VERIFIED_LABEL = 1  # flip on F2P by construction
SMITH_NEGATIVE_LABEL = 0


def build_matrix(
    positives_path: Path,
    negatives_path: Path,
    smith_tasks_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    """Fuse the two classes into arm inputs. Every row: instance_id, repo,
    patch, problem_statement, FAIL_TO_PASS, label, source."""
    pos = json.loads(Path(positives_path).read_text())
    neg = json.loads(Path(negatives_path).read_text())
    smith_tasks = json.loads(Path(smith_tasks_path).read_text())
    task_by_id = {t["instance_id"]: t for t in smith_tasks}

    rows: list[dict[str, Any]] = []
    for it in pos:
        rows.append(
            {
                "instance_id": f"verified::{it['instance_id']}",
                "repo": it["repo"],
                "patch": it["patch"],
                "problem_statement": it.get("problem_statement", ""),
                "FAIL_TO_PASS": it.get("FAIL_TO_PASS", []),
                "label": VERIFIED_LABEL,
                "source": "swe-bench-verified",
            }
        )
    missed_join = 0
    for it in neg:
        t = task_by_id.get(it["instance_id"])
        if not t:
            missed_join += 1
            continue
        rows.append(
            {
                "instance_id": f"smith::{it['instance_id']}::{it['model']}",
                "repo": t.get("repo", ""),
                "patch": it["patch"],
                "problem_statement": t.get("problem_statement", ""),
                "FAIL_TO_PASS": t.get("FAIL_TO_PASS", []),
                "label": SMITH_NEGATIVE_LABEL,
                "source": "swe-smith-trajectories",
            }
        )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n")
    manifest = {
        "rows": len(rows),
        "positives": sum(1 for r in rows if r["label"] == VERIFIED_LABEL),
        "negatives": sum(1 for r in rows if r["label"] == SMITH_NEGATIVE_LABEL),
        "missed_join": missed_join,
        "repos": sorted({r["repo"] for r in rows}),
    }
    (out_path.parent / "matrix-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
