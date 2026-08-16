#!/usr/bin/env python3
"""Window coverage-ts-v7 — staging multi-sources (zod + date-fns) : quota validé
zéro-appel -> campagne coverage-ts-7. Chaque tâche porte son repo + sa target
relative ; le label exec route le runner vitest par repo.
Run: uv run python scripts/act2/ts_v7_stage.py
"""
from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "landing" / "act2-pilot" / "ts-v7"
OUT = ROOT / "data" / "landing" / "act2-pilot" / "coverage-ts-7"


def main() -> int:
    mani = json.loads((SRC / "quota-tasks.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for t in mani["tasks"]:
        iid = t["instance_id"]
        buggy = SRC / f"{iid.replace('/', '_')}.buggy.py"
        if not buggy.is_file():
            print(f"ABORT: buggy source absente {iid}")
            return 2
        if sha256(buggy.read_bytes()).hexdigest() != t["buggy_sha256"]:
            print(f"ABORT: buggy source corrompue {iid}")
            return 2
        (OUT / f"{iid.replace('/', '_')}.buggy.py").write_text(buggy.read_text())
        rows.append({
            "instance_id": iid, "repo": t["repo"],
            "family": iid.split(".")[0],
            "campaign": "coverage-ts-7", "window": "coverage-ts-v7",
            "lang": "typescript", "image": None, "patch": "",
            "buggy_file_target": t["target"], "f2p": t["f2p"],
            "p2p_n": t["p2p_n"], "problem": t["problem"],
            "target": t["target"], "spec": t["spec"], "tier": t.get("tier"),
        })
    blob = json.dumps({"window": "coverage-ts-v7",
                       "quota_manifest_sha256": sha256(
                           (SRC / "quota-tasks.json").read_bytes()).hexdigest(),
                       "tasks": rows, "quarantined": []},
                      indent=1, sort_keys=True)
    (OUT / "staging-extract.json").write_text(blob + "\n")
    print(f"staging v7: {len(rows)} tâches -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
