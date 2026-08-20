#!/usr/bin/env python3
"""Archivage des trajectoires labelisées (paradigme 2) — asset données.

Consolide v30 (patchs agents MSWB mesurés) + v32/v33/v34/v35 (boucles
agentiques internes) en un store unique : par instance, la séquence des
états (patch, appliqué ?, tests échoués, y). Pour futurs modèles séquentiels.
Run: uv run python scripts/futures/trajectory_archive.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NH = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest"
MSWB = ROOT / "data" / "landing" / "act2-pilot" / "mswb"
OUT = ROOT / "data" / "landing" / "act2-pilot" / "trajectories"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    store: dict = defaultdict(list)
    # v30 : patchs d'agents externes mesurés (1 shot par agent)
    f = MSWB / "vuejs__core" / "agent-measured.json"
    if f.is_file():
        for m in json.loads(f.read_text()):
            store[m["instance"]].append({
                "window": "v30-mswb-trajs", "agent": m.get("agent"), "model": m.get("model"),
                "turn": 0, "applied": m["applied"], "y": m["y"],
                "failed_tests": m.get("failed_all", []), "n_passed": m.get("n_passed")})
    # v32-v35 : boucles internes
    for v in ("v32", "v33", "v34", "v35"):
        rf = NH / f"replay-rows-{v}.jsonl"
        if not rf.is_file():
            continue
        for l in rf.read_text().splitlines():
            if not l.strip():
                continue
            r = json.loads(l)
            if r["id"].startswith(f"{v}-setup"):
                continue
            store[r["issue"]].append({
                "window": v, "model": r.get("model", "?"), "turn": r.get("turn"),
                "applied": bool(r.get("applied")), "apply_mode": r.get("apply_mode"),
                "y": r.get("y"), "failed_tests": r.get("failed_all", []),
                "n_passed": r.get("n_passed"), "finish_reason": r.get("finish_reason")})
    for k in list(store):
        store[k].sort(key=lambda e: (e["window"], str(e.get("model")), e.get("turn") or 0))
    n_steps = sum(len(v) for v in store.values())
    resolved = {k: sorted({e["window"] for e in v if e.get("y") == 1}) for k, v in store.items()}
    n_res = sum(1 for v in resolved.values() if v)
    (OUT / "trajectories.json").write_text(json.dumps(dict(sorted(store.items())), indent=1, ensure_ascii=False) + "\n")
    (OUT / "resolutions.json").write_text(json.dumps({k: v for k, v in sorted(resolved.items()) if v}, indent=1) + "\n")
    print(json.dumps({"instances": len(store), "etapes": n_steps,
                      "instances_resolues_par_au_moins_un_systeme": n_res}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
