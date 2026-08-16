#!/usr/bin/env python3
"""Story 10.2 — embeddings genfam (node, unixcoder-base, même classe qu'embed_pool).

Recettes GELÉES par référence (embed_pool.py) :
  E_state = problem[:1200] + "\n" + "; ".join(f2p[:6])
  E_diff  = le diff généré (diff.patch du slot)
  E_goal  = zéro EXPLICITE (goal_free=True, précédé par flywheel_embed ; l'axe
            gold ne doit jamais consommer ces lignes)
Seuls les slots ÉTIQUETÉS (run-result présent + label émis) deviennent des
candidats-lignes ; jamais d'invention de lignes non mesurées.

Sortie: genfam-q1/genfam-q1-embed.npz + genfam-q1-rows.json
Run (node): python3 scripts/act2/genfam_embed.py --quota q1
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

BASE = Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot")
_spec = importlib.util.spec_from_file_location("s11", Path(__file__).resolve().parent / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quota", default="q1")
    ap.add_argument("--dir", default=None,
                    help="répertoire campagne sous act2-pilot (défaut genfam-<quota>)")
    args = ap.parse_args()
    cdir = args.dir or f"genfam-{args.quota}"
    q = BASE / cdir
    staging = {t["instance_id"]: t for t in
               json.loads((q / "staging-extract.json").read_text())["tasks"]}
    labels = json.loads((q / "labels" / "genfam-label-report.json").read_text())
    lab_by_slot = {p["attempt_id"]: p for p in labels["provenance"] if p["layer"] == "label"}
    if not lab_by_slot:
        print("aucun label émis — la classification doit passer d'abord")
        return 1

    rows = []
    for slot_dir in sorted((q / "gen-results").glob("*-d*")):
        rr = slot_dir / "run-result.json"
        dp = slot_dir / "diff.patch"
        lbl = lab_by_slot.get(slot_dir.name)
        if not (rr.is_file() and dp.is_file() and lbl):
            continue  # slot non mesuré / pas de diff / quarantaine : pas une ligne
        res = json.loads(rr.read_text())
        if not res.get("patch_applied"):
            continue  # jamais étiqueté valide par la chaîne ; hors lignes embed
        st = staging[res["task"]]
        diff = dp.read_text()
        if not diff.strip():
            continue
        rows.append({
            "task": res["task"], "slot": slot_dir.name,
            "family": st["instance_id"].split(".")[0],
            "campaign": res.get("campaign", f"genfam-{args.quota}"),
            "window": "gen-families-v1", "author": res.get("author"),
            "draw": res.get("draw"),
            "state": st["problem"][:1200] + "\n" + "; ".join(map(str, st["f2p"][:6])),
            "diff": diff, "gold": "",
            "y": lbl["y"], "goal_free": True,
            "diff_sha256": res.get("diff_sha256") or lbl.get("diff_sha256"),
        })
    if not rows:
        print("aucune ligne à embed")
        return 1

    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer

    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    model = AutoModel.from_pretrained("microsoft/unixcoder-base").eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    print(f"embed {len(rows)} lignes {cdir} sur {device}", flush=True)
    E_s = s11.batched_embed(model, tok, [r["state"] for r in rows])
    E_d = s11.batched_embed(model, tok, [r["diff"] for r in rows])
    E_g = np.zeros((len(rows), E_s.shape[1]), dtype=E_s.dtype)  # goal_free : zéro explicite

    np.savez_compressed(q / f"{cdir}-embed.npz", E_state=E_s, E_diff=E_d, E_goal=E_g)
    meta = [{k: r[k] for k in ("task", "slot", "family", "campaign", "window",
                               "author", "draw", "y", "goal_free", "diff_sha256")}
            for r in rows]
    (q / f"{cdir}-rows.json").write_text(json.dumps(meta, indent=1) + "\n")
    pos = sum(r["y"] for r in rows)
    print(f"OK : {len(rows)} lignes ({pos} positives, {len(rows) - pos} négatives) "
          f"-> {q.name}/{cdir}-embed.npz ({E_s.shape[1]}-d)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
