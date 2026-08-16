#!/usr/bin/env python3
"""Window coverage-ts-v5 — staging : quota-tasks validés → répertoire campagne
coverage-ts-5 (staging-extract.json + buggy sources) pour le harness budget.
La labellisation appliquera le fichier buggy par scp (pas de git-apply du bug :
le contenu buggy EST l'état infecté, vérifié à la construction du quota).
Run: uv run python scripts/act2/ts_v2_stage.py
"""
from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "landing" / "act2-pilot" / "ts-v5"
OUT = ROOT / "data" / "landing" / "act2-pilot" / "coverage-ts-5"


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
            "instance_id": iid, "family": "kimsufi__site",
            "campaign": "coverage-ts-5", "window": "coverage-ts-v5",
            "lang": "typescript", "image": None,
            "patch": "",  # l'infection se fait par copie du fichier buggy (scp)
            "buggy_file_target": t["target"],
            "f2p": t["f2p"], "p2p_n": t["p2p_n"],
            "problem": t["problem"], "target": t["target"], "spec": t["spec"],
        })
    blob = json.dumps({"window": "coverage-ts-v5",
                       "quota_manifest_sha256": sha256(
                           (SRC / "quota-tasks.json").read_bytes()).hexdigest(),
                       "tasks": rows, "quarantined": []},
                      indent=1, sort_keys=True)
    (OUT / "staging-extract.json").write_text(blob + "\n")
    print(f"staging: {len(rows)} tâches → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
