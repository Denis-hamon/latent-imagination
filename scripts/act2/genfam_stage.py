#!/usr/bin/env python3
"""Story 10.1 — staging genfam pour extraction node (buggy-src).

Depuis la sélection gelée (governance/act2/genfam-q1-selection-v1.json) +
les parquets raw SWE-smith locaux, produit UN fichier de staging
(data/landing/act2-pilot/genfam-q1/staging-extract.json) autosuffisant pour le
node : instance_id, family, image, patch (diff bug-inducteur), f2p, problem,
target (dérivé du patch — UN seul fichier touché exigé, classe prompt gelée).

Multi-fichier ou patch sans chemin b/ ⇒ quarantaine déclarée dans le staging
(disclose, jamais de devinette de target).

Run: uv run python scripts/act2/genfam_stage.py
"""
from __future__ import annotations

import json
import re
import sys
from hashlib import sha256
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "landing" / "swe-smith-tasks" / "raw"
SEL = ROOT / "governance" / "act2" / "genfam-q1-selection-v1.json"
OUT_DIR = ROOT / "data" / "landing" / "act2-pilot" / "genfam-q1"
OUT = OUT_DIR / "staging-extract.json"

B_PATH = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


def _target(patch: str) -> str | None:
    paths = sorted(set(B_PATH.findall(patch)))
    return paths[0] if len(paths) == 1 else None


def main() -> int:
    sel_bytes = SEL.read_bytes()
    sel = json.loads(sel_bytes)
    sel_digest = sha256(sel_bytes).hexdigest()  # seal = sha256 des octets du fichier

    parq: dict[str, dict] = {}
    for f in sorted(RAW.glob("train-*.parquet")):
        for r in pq.read_table(
                str(f), columns=["instance_id", "patch", "FAIL_TO_PASS",
                                 "image_name", "problem_statement"]).to_pylist():
            parq.setdefault(r["instance_id"], r)

    tasks, quarantined = [], []
    for row in sel["q1"]:
        iid = row["instance_id"]
        p = parq.get(iid)
        if p is None or not p["patch"]:
            quarantined.append({"instance_id": iid, "reason": "absent du raw local"})
            continue
        tgt = _target(p["patch"])
        if tgt is None:
            n = len(set(B_PATH.findall(p["patch"])))
            quarantined.append({"instance_id": iid,
                                "reason": f"patch touche {n} fichiers (target unique exigé)"})
            continue
        tasks.append({
            "instance_id": iid,
            "family": row["family"],
            "campaign": "genfam-q1",
            "window": "gen-families-v1",
            "image": p["image_name"],
            "patch": p["patch"],
            "f2p": list(p["FAIL_TO_PASS"]),
            "problem": p["problem_statement"].strip(),
            "target": tgt,
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps({"window": "gen-families-v1",
                       "selection_digest": sel_digest,
                       "tasks": tasks,
                       "quarantined": quarantined},
                      indent=1, sort_keys=True)
    OUT.write_text(blob + "\n")
    print(f"staging: {len(tasks)} tâches à extraire, {len(quarantined)} en quarantaine "
          f"(digest sélection {sel_digest[:16]}), -> {OUT.relative_to(ROOT)}")
    for q in quarantined:
        print(f"  QUARANTAINE: {q['instance_id']} — {q['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
