"""P10 — transitions v39 construites depuis le rejeu P12.

Une transition = une paire de tours CONSÉCUTIFS d'une même trajectoire, au
format exact de `v39-transitions.jsonl` : c'est ce format que le pipeline de fit
de w46 consomme, et le contrôle positif exige que le MÊME code lise les deux
corpus. Rien n'est recalculé ici, tout vient du rejeu gelé.

ZÉRO appel LLM.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Meme fichier pour P12 et P14, pilote par variable d'environnement — comme
# p12_replay.py et p12_gates.py. Dupliquer aurait fait diverger en silence.
CORPUS = os.environ.get("LI_CORPUS", "p12")
B = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / f"py-{CORPUS}"
OUT = B / f"{CORPUS}-transitions.jsonl"
# solveur amont unique de la source SWE-rebench-openhands-trajectories
MODELE = "Qwen3-Coder-480B-A35B-Instruct"


def main() -> int:
    sel = {x["instance_id"]: x for x in json.loads((B / f"{CORPUS}-selection.json").read_text())}
    lignes = []
    for f in sorted((B / f"{CORPUS}-replay").glob("*.json")):
        d = json.loads(f.read_text())
        iid = d["instance_id"]
        decl = sorted(set(sel[iid]["FAIL_TO_PASS"]))
        for ti, traj in enumerate(d.get("trajectories", [])):
            # un tour n'entre que s'il a été MESURÉ : patch réellement dans
            # l'arbre, sortie pytest parsée, tests déclarés tous observés.
            ok = [t for t in traj if t.get("applied") and t.get("parsed")
                  and not t.get("declares_non_observes")]
            for a, b in zip(ok, ok[1:]):
                rf, rt = sorted(set(a["failed_all"])), sorted(set(b["failed_all"]))
                lignes.append({
                    "key": f"{CORPUS}-{iid}-t{ti}-{a['turn']}>{b['turn']}",
                    "instance": iid,
                    "window": "p12",
                    "model": MODELE,
                    "repo": d["repo"],
                    "trajectory_id": b.get("trajectory_id"),
                    "turn_from": a["turn"], "turn_to": b["turn"],
                    "declared": decl,
                    "red_from": rf, "red_to": rt,
                    "red_from_dec": [x for x in decl if x in set(rf)],
                    "red_to_dec": [x for x in decl if x in set(rt)],
                    # `diff_to` est DÉJÀ tronqué à 8000 dans le rejeu, comme en v39
                    "diff_to": b.get("diff", ""),
                    "changed": a.get("diff") != b.get("diff"),
                })
    OUT.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lignes))
    npos = sum(1 for t in lignes for x in t["declared"] if x in set(t["red_to"]))
    npair = sum(len(t["declared"]) for t in lignes)
    print(f"{len(lignes)} transitions · {npair} paires test×transition · {npos} positives")
    print(f"instances {len({t['instance'] for t in lignes})} · "
          f"trajectoires {len({(t['instance'], t['key'].rsplit('-', 1)[0]) for t in lignes})}")
    print(f"écrit : {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
