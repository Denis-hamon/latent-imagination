#!/usr/bin/env python3
"""Story 14.3 — staging de la fenêtre TS : manifeste validé → répertoire
campagne coverage-ts-1 prêt pour le harness budget (même forme que
genfam_stage.py : staging-extract.json autosuffisant + fichiers buggy).

Le manifeste est le résultat VÉRIFIÉ du builder ts14_tasks.py (F2P/P2P
prouvés, gold reverdit) ; le staging ne réinvente rien, il transporte.
Run: uv run python scripts/act2/ts14_stage.py
"""
from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "data" / "landing" / "act2-pilot" / "ts14-pilot"
SRC = SRC_DIR / "ts14-tasks.json"
OUT_DIR = ROOT / "data" / "landing" / "act2-pilot" / "coverage-ts-1"


def main() -> int:
    mani = json.loads(SRC.read_text())
    tasks = mani["tasks"]
    if not tasks:
        print("manifeste vide")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for t in tasks:
        iid = t["instance_id"]
        buggy = (SRC_DIR / f"{iid.replace('/', '_')}.buggy.py")
        if not buggy.is_file():
            print(f"ABORT: buggy source absente pour {iid}")
            return 2
        content = buggy.read_text()
        if sha256(content.encode()).hexdigest() != t["buggy_sha256"]:
            print(f"ABORT: buggy source corrompue pour {iid} (hash ≠ manifeste)")
            return 2
        (OUT_DIR / f"{iid.replace('/', '_')}.buggy.py").write_text(content)
        rows.append({
            "instance_id": iid,
            "family": "acre__blocks",
            "campaign": "coverage-ts-1",
            "window": "coverage-ts-v1",
            "lang": "typescript",
            "patch": t["patch"],
            "f2p": t["f2p"],
            "p2p": t["p2p"],
            "problem": t["problem"],
            "target": t["target"],
            "test": t["test"],
        })
    blob = json.dumps({"window": "coverage-ts-v1",
                       "manifest_sha256": sha256(SRC.read_bytes()).hexdigest(),
                       "tasks": rows, "quarantined": []},
                      indent=1, sort_keys=True)
    (OUT_DIR / "staging-extract.json").write_text(blob + "\n")
    print(f"staging: {len(rows)} tâches TS → {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
