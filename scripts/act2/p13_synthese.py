#!/usr/bin/env python3
"""P13 — synthèse : lit tous les artefacts de variantes et applique la grille GELÉE.

Fenêtre `governance/act2/window-p13-scamper-proposal.md`. Aucun calcul de modèle
ici : uniquement de la lecture, pour que le verdict soit rejouable sans refitter.

  G1 GAGNANT : AUC⊥ > barre du max ET >= 0,65 ET leave-one-repo-out >= 0,60 partout
  G2 PISTE   : franchit la barre, échoue le LORO ou le seuil absolu
  G3 NUL     : sinon

Usage : .venv/bin/python scripts/act2/p13_synthese.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
P13 = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / "py-p12" / "p13"
ORDRE = [f"V{k}" for k in range(1, 14)]
REF_C50 = {"w46": {"V1": 0.8333, "V2": 0.8704, "V3": 0.6296},
           "p12": {"V1": 0.4793, "V2": 0.5372, "V3": 0.5455}}
NEG_UN_TIRAGE = {"p12": 0.5372}  # UN SEUL tirage de permutation (bras NEG-intra-inst
                                 # du fit p10), PAS la nulle : celle-ci vient des 200
                                 # permutations de `p13_nulle.py`. Ne jamais lire ce
                                 # nombre comme une barre.


def lit(corpus: str) -> dict:
    out = {}
    for f in sorted(P13.glob(f"p13-{corpus}-*.json")):
        for vid, r in json.load(open(f))["variantes"].items():
            out[vid] = r
    return out


def barre() -> dict | None:
    f = P13 / "nulle-du-max-p12.json"
    return json.load(open(f)) if f.is_file() else None


def main() -> int:
    W, P = lit("w46"), lit("p12")
    b = barre()
    print("P13 — AUC⊥ (strate où `persist` est aveugle : 54 paires w46, 121 paires P12)")
    print("      AUC⊥⊥ entre parenthèses : sous-strate « même test, deux patchs »\n")
    print(f"{'id':4s} {'variante':34s} {'w46 ⊥':>16s} {'P12 ⊥':>16s} {'IC95 P12':>18s}")
    print("-" * 92)
    for v in ORDRE:
        w, p = W.get(v), P.get(v)
        def cel(r, c):
            if not r:
                return "—"
            s = r["strates"]
            return f"{s['aveugle']['auc']:.4f} ({s['aveugle_meme_test']['auc']:.2f})"
        lib = (w or p or {}).get("libelle", "?")
        ic = str(p["ic95_aveugle"]) if p else "—"
        print(f"{v:4s} {lib:34s} {cel(w,'w46'):>16s} {cel(p,'p12'):>16s} {ic:>18s}")
    print("-" * 92)
    print(f"{'':4s} {'référence C=50 (avant P13)':34s} "
          f"{REF_C50['w46']['V1']:>16.4f} {REF_C50['p12']['V1']:>16.4f}")
    print(f"{'':4s} {'UN tirage de permutation (pas la barre)':34s} {'—':>16s} "
          f"{NEG_UN_TIRAGE['p12']:>16.4f}")

    vals = {v: P[v]["strates"]["aveugle"]["auc"] for v in P}
    meilleur = max(vals, key=vals.get)
    print(f"\nMEILLEURE VARIANTE SUR P12 : {meilleur} = {vals[meilleur]:.4f}"
          f"  ({len(vals)} variantes jouées sur 13 gelées)")
    if b is None:
        print("BARRE NON ENCORE MESURÉE — lancer `p13_nulle.py` avant tout verdict.")
        return 0
    B = b["barre_exacte_du_max_p95"]
    print(f"BARRE EXACTE DU MAX (p95, {b['n_permutations']} permutations) : {B:.4f}")
    print(f"barre Bonferroni K=13 conservatrice : {b['barre_bonferroni_conservatrice']:.4f}")
    issue = ("G1/G2 — à départager par le leave-one-repo-out"
             if vals[meilleur] > B else "G3 — aucune variante ne franchit la barre")
    print(f"\nVERDICT : {issue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
