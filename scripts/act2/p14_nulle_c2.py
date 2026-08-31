#!/usr/bin/env python3
"""Nulle de C2 — le contenu JS/TS transfere-t-il, oui ou non ?

DECLARE AVANT D'ETRE JOUE, dans `window-p14-variance-proposal.md`, section
« Prochaine mesure, declaree AVANT d'etre jouee » :

  C2 au-dessus du p95 de sa nulle  -> le transfert inter-langage est un fait
                                      mesure. Ouvre une fenetre de decision.
  C2 sous ce p95                   -> pas de transfert. Tout le signal de V13
                                      est un effet de taille et de prior.

LE DISPOSITIF. C2 ajuste un modele sur w46 SEUL (747 lignes JS/TS, zero ligne
Python) et note les paires aveugles de P14. Sa nulle permute les labels de w46
avant le fit, cent fois. C'est le seul montage qui isole le CONTENU de w46 :
  - il n'y a pas de fit Python, donc l'effet de taille ne s'applique pas ;
  - sur la strate aveugle, `persist` est constant par construction, donc le
    classement ne peut venir que de la geometrie Ed/Et/cos ;
  - les labels de P14 ne sont JAMAIS touches, donc la strate aveugle est fixe
    d'un tirage a l'autre — contrairement a la nulle intra-instance, ou le jeu
    de paires doit etre recalcule a chaque fois.

Mesure DESCRIPTIVE. Elle ne touche pas la grille R1/R2/R3 : R3 est acquis.

Usage : .venv/bin/python scripts/act2/p14_nulle_c2.py --perms 100 --workers 15
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "act2"))

import p13_metrics as M       # noqa: E402
import p13_variants as V      # noqa: E402

C_FIXE = 50.0
_W: dict = {}


def _init():
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[v] = "1"
    D = M.charge("p14")
    B = V.blocs("p14")
    Xp = np.concatenate([B["Ed"], B["Et"], B["cos"], B["scal"]], axis=1)
    _W["Xp"] = np.hstack([Xp, np.ones((len(Xp), 1))])
    Xw = np.load(V.P10 / "_X-w46.npy")
    _W["Xw"] = np.hstack([Xw, np.zeros((len(Xw), 1))])
    _W["yw"] = np.load(V.P10 / "_y-w46.npy")
    _W["y"] = np.load(V.P10 / "_y-p14.npy")
    _W["D"] = D


def _auc_perp(p) -> float:
    return M.toutes_strates(p, _W["D"])["aveugle"]["auc"]


def _task(graine: int) -> float:
    rng = np.random.default_rng(graine)
    ypm = _W["yw"][rng.permutation(len(_W["yw"]))]
    if ypm.sum() in (0, len(ypm)):
        return float("nan")
    return _auc_perp(V._fit(C_FIXE, _W["Xw"], ypm, _W["Xp"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--perms", type=int, default=100)
    ap.add_argument("--workers", type=int, default=15)
    a = ap.parse_args()

    _init()
    obs = _auc_perp(V._fit(C_FIXE, _W["Xw"], _W["yw"], _W["Xp"]))
    print(f"C2 observe (w46 seul, vrais labels) : AUC⊥ {obs:.4f}", flush=True)
    print(f"w46 : {len(_W['yw'])} lignes, {int(_W['yw'].sum())} positives · "
          f"P14 : {len(_W['y'])} lignes\n", flush=True)

    graines = [11000 + k for k in range(a.perms)]
    with cf.ProcessPoolExecutor(max_workers=a.workers, initializer=_init) as ex:
        vals = [v for v in ex.map(_task, graines) if not np.isnan(v)]

    n = np.array(vals)
    p95 = float(np.percentile(n, 95))
    sup = int((n >= obs).sum())
    print(f"nulle sur {len(n)} permutations des labels w46 :")
    print(f"  moyenne {n.mean():.4f} ± {n.std(ddof=1):.4f} · min {n.min():.4f} · max {n.max():.4f}")
    print(f"  p95 {p95:.4f} · p99 {np.percentile(n, 99):.4f}")
    print(f"\n  C2 observe {obs:.4f} · tirages >= observe : {sup}/{len(n)}")
    print(f"  p empirique {(sup + 1) / (len(n) + 1):.4f}")
    verdict = "TRANSFERT MESURE" if obs > p95 else "PAS DE TRANSFERT"
    print(f"\n  => {verdict} (lecture pre-declaree dans la fenetre P14)")

    rap = {"at": datetime.now(UTC).isoformat(), "corpus": "p14",
           "fenetre": "governance/act2/window-p14-variance-proposal.md",
           "dispositif": "fit sur w46 seul, labels w46 permutes, note sur les paires aveugles de P14",
           "C": C_FIXE, "n_w46": int(len(_W["yw"])), "n_p14": int(len(_W["y"])),
           "C2_observe": obs, "n_permutations": int(len(n)),
           "nulle_moyenne": float(n.mean()), "ecart_type": float(n.std(ddof=1)),
           "p95": p95, "max": float(n.max()),
           "tirages_au_dessus_ou_egal": sup,
           "p_empirique": (sup + 1) / (len(n) + 1),
           "verdict": verdict, "tirages": n.tolist()}
    f = V.OUT / "nulle-c2-p14.json"
    f.write_text(json.dumps(rap, ensure_ascii=False, indent=1))
    print(f"\necrit : {f}\nsha256 : {hashlib.sha256(f.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
