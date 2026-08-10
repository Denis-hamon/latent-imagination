#!/usr/bin/env python3
"""Construit l'eval pack public frozen32 pour latent-gate.

Contenu publié (licite, déjà miroir des releases publiques du projet) :
  eval-tasks.jsonl — par ligne : {task, state, goal, candidates:[{arm, diff, y}]}
  candidates = patchs réels LLM de la fenêtre gelée (arms on/off), y = verdict
  F2P exécuté (docker, protocole du pilot act2).

IMPORTANT — falsifiabilité sans fuite : le runner public appelle le service
AVEC exclude_task=<task> : le serveur retire tout le pool de cette tâche avant
de scorer. La mesure publique est donc LOAO par construction. Toute utilisation
SANS exclude_task est in-sample et doit être lue comme telle (affiché dans le
rapport d'éval).

Run : python build_eval_pack.py --pilot-dir data/landing/act2-pilot --out <ici>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-dir", default="data/landing/act2-pilot")
    ap.add_argument("--out", default=str(Path(__file__).parent))
    args = ap.parse_args()
    base = Path(args.pilot_dir)
    tasks = {t["instance_id"]: t
             for t in json.loads((base / "pilot-tasks-frozen32.json").read_text())}
    out = Path(args.out)

    n_tasks, n_cand = set(), 0
    lines = []
    for results_dir in ("results", "results-v2"):
        rdir = base / results_dir
        if not rdir.is_dir():
            continue
        for slot in sorted(rdir.glob("*")):
            mf, pf, rf = slot / "meta.json", slot / "patch.diff", slot / "run-result.json"
            if not (mf.is_file() and pf.is_file() and rf.is_file()):
                continue
            m = json.loads(mf.read_text())
            r = json.loads(rf.read_text())
            ptxt = pf.read_text()
            if not (r.get("patch_applied") and ptxt.strip()):
                continue
            t = tasks[m["task"]]
            goldf = base / "control-gold" / m["task"].replace("/", "_") / "gold.diff"
            if not goldf.is_file():
                continue
            n_tasks.add(m["task"])
            n_cand += 1
            lines.append({"task": m["task"], "arm": m.get("arm"),
                          "window": results_dir,
                          "state": (t["problem"][:1200] + "\n"
                                    + "; ".join(map(str, t["f2p"][:6]))),
                          "goal": goldf.read_text(),
                          "diff": ptxt,
                          "y": 1 if r.get("f2p_pass") else 0})

    # regrouper par tâche
    by_task: dict[str, dict] = {}
    for L in lines:
        e = by_task.setdefault(L["task"], {"task": L["task"], "state": L["state"],
                                           "goal": L["goal"], "candidates": []})
        e["candidates"].append({"arm": L["arm"], "window": L["window"],
                                "diff": L["diff"], "y": L["y"]})

    f = out / "eval-tasks.jsonl"
    with f.open("w") as fh:
        for task in sorted(by_task):
            fh.write(json.dumps(by_task[task]) + "\n")
    print(f"eval pack : {len(by_task)} tâches, {n_cand} candidats → {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
