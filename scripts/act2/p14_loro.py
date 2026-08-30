#!/usr/bin/env python3
"""LORO (leave-one-repo-out) — pilote de `p13_variants.loro`.

POURQUOI CE FICHIER EXISTE. `loro()` a ete ecrit dans `p13_variants.py` le
2026-08-29 avec sa precondition de lisibilite, puis **jamais appele** : ni
option CLI, ni invocation dans `main()`. Le critere que la grille R2 exige
etait donc du code mort. Ce pilote le branche.

Il est SEPARE et n'edite pas `p13_variants.py` a dessein : la nulle du maximum
tourne et importe ce module ; le modifier pendant qu'elle tourne changerait le
banc sous ses pieds.

COUVERTURE. `LORO_BLOCS` ne couvre que V1, V2, V3, V6, V11, V14 — les deux
familles ou un fit unique hors-depot est derivable. V4 ajuste une PCA dans le
pli, V5 une fusion tardive, V12 une stratification, V13 un corpus conjoint : le
LORO n'y est pas le meme objet. Cette couverture est GELEE avant le rejeu ; elle
n'est pas elargie apres coup au vu du classement.

Usage : .venv/bin/python scripts/act2/p14_loro.py --corpus p14
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "act2"))

import p13_metrics as M  # noqa: E402
import p13_variants as V  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=("w46", "p12", "p14"), required=True)
    ap.add_argument("--variantes", default=",".join(sorted(V.LORO_BLOCS)))
    a = ap.parse_args()

    D = M.charge(a.corpus)
    B = V.blocs(a.corpus)
    y = np.load(V.P10 / f"_y-{a.corpus}.npy")
    assert len(y) == B["X"].shape[0] == len(D["y"]) and (y == D["y"]).all(), \
        "desynchronisation entre le cache p10 et le chargement p13"

    vids = [v.strip() for v in a.variantes.split(",") if v.strip()]
    print(f"corpus {a.corpus} · {len(y)} lignes · variantes {','.join(vids)}", flush=True)
    print(f"precondition de lisibilite : >= {V.LORO_MIN_INSTANCES} instances "
          f"ET >= {V.LORO_MIN_PAIRES} paires aveugles portees par le depot\n", flush=True)

    rap = {"at": datetime.now(UTC).isoformat(), "corpus": a.corpus,
           "fenetre": "governance/act2/window-p14-variance-proposal.md",
           "seuil": 0.60, "min_instances": V.LORO_MIN_INSTANCES,
           "min_paires": V.LORO_MIN_PAIRES, "variantes": {}}

    for vid in vids:
        r = V.loro(vid, a.corpus, B, y, D, M)
        rap["variantes"][vid] = r
        if not r.get("couvert"):
            print(f"{vid:5s} NON COUVERT — {r.get('raison')}", flush=True)
            continue
        lis = [d for d, v in r["par_depot"].items() if v.get("lisible")]
        print(f"{vid:5s} famille {r['famille']:12s} depots lisibles {len(lis)}/{len(r['par_depot'])}",
              flush=True)
        for dep, v in sorted(r["par_depot"].items()):
            if v.get("lisible"):
                verdict = "SATISFAIT" if v["auc"] >= 0.60 else "ECHOUE"
                print(f"        {dep:22s} AUC⊥ {v['auc']:.4f}  "
                      f"({v['paires']} paires / {v['instances']} inst.)  {verdict}", flush=True)
            else:
                print(f"        {dep:22s} NON EVALUABLE  "
                      f"({v['paires']} paires / {v['instances']} inst.)"
                      f"{' — ' + v['raison'] if v.get('raison') else ''}", flush=True)

    f = V.OUT / f"loro-{a.corpus}.json"
    f.write_text(json.dumps(rap, ensure_ascii=False, indent=1))
    print(f"\necrit : {f}\nsha256 : {hashlib.sha256(f.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
