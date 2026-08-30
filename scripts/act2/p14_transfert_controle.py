#!/usr/bin/env python3
"""V13 : transfert inter-langage, ou simple effet de taille d'echantillon ?

LA QUESTION. V13 ajoute w46 (JS/TS) a l'entrainement et fait passer la strate
aveugle Python de ~0,50 a 0,6897. Deux explications concurrentes, que le
resultat de V13 ne separe PAS :

  (a) TRANSFERT — la structure JS/TS informe la prediction Python ;
  (b) TAILLE / PRIOR — on ajoute 747 lignes (dont 30 positives seulement, 4 %)
      a une regression logistique en 1540 dimensions ajustee sur 1009 lignes a
      38,6 % de positifs. L'indicatrice de corpus absorbe le decalage de niveau,
      mais les lignes ajoutees tirent quand meme le modele partage vers le
      negatif et le regularisent. Aucun transfert de sens n'est requis.
      (Chiffres MESURES au lancement : ne pas les deduire du nombre de PAIRES de
      w46, 21 510, qui est une autre quantite — c'est l'erreur que ce commentaire
      corrige.)

LES CONTROLES. Un seul les separe vraiment :

  C1 — w46 a LABELS PERMUTES. Memes lignes, meme geometrie, meme nombre, mais
       les labels JS/TS ne veulent plus rien dire. Si l'AUC-PERP tient, c'est
       (b) : ce sont les lignes qui aident, pas ce qu'elles disent. Si elle
       s'effondre vers 0,50, c'est (a).
  C2 — w46 SEUL, zero Python en entrainement. Transfert a l'etat pur. Une AUC
       au-dessus de la nulle ici serait un transfert que rien d'autre n'explique.
  C0 — V13 rejoue, pour que C1 et C2 se lisent contre une valeur reproduite ici
       et non contre une valeur recopiee d'un autre journal.

Ces controles etaient PREVISIBLES avant de voir le resultat de V13 : ils ne
changent aucun seuil et ne touchent pas la grille R1/R2/R3. Ils disent ce que
R3 VOUDRAIT DIRE, pas s'il est atteint.

Usage : .venv/bin/python scripts/act2/p14_transfert_controle.py --corpus p14
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "act2"))

import p13_metrics as M       # noqa: E402
import p13_variants as V      # noqa: E402

C_FIXE = 50.0                 # convention v39/v41, la meme que V13


def _xw_yw():
    Xw = np.load(V.P10 / "_X-w46.npy")
    yw = np.load(V.P10 / "_y-w46.npy")
    return np.hstack([Xw, np.zeros((len(Xw), 1))]), yw


def _xp(B):
    Xp = np.concatenate([B["Ed"], B["Et"], B["cos"], B["scal"]], axis=1)
    return np.hstack([Xp, np.ones((len(Xp), 1))])


def conjoint(B, y, g, folds, yw_source):
    """V13 generique : `yw_source` fournit les labels w46 (vrais ou permutes)."""
    Xp, (Xw, _) = _xp(B), _xw_yw()
    yw = yw_source
    p = np.zeros(len(y))
    for gg in folds:
        te = g == gg
        tr = ~te
        Xa = np.vstack([Xp[tr], Xw])
        ya = np.r_[y[tr], yw]
        p[te] = V._fit(C_FIXE, Xa, ya, Xp[te])
    return p


def w46_seul(B, y, g, folds):
    """Zero ligne Python en entrainement. Un seul fit, aucun pli necessaire."""
    Xp, (Xw, yw) = _xp(B), _xw_yw()
    return V._fit(C_FIXE, Xw, yw, Xp)


def lis(nom, p, D, res):
    r = M.toutes_strates(p, D)
    lo, hi = M.bootstrap_ci(p, D, "aveugle")
    res[nom] = {"strates": r, "ic95_aveugle": [lo, hi]}
    print(f"  {nom:34s} ⊥ {r['aveugle']['auc']:.4f}  IC95 [{lo}, {hi}]"
          f"  ⊥⊥ {r['aveugle_meme_test']['auc']}  toutes {r['toutes']['auc']}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=("p12", "p14"), default="p14")
    ap.add_argument("--graines", type=int, default=5)
    a = ap.parse_args()

    D = M.charge(a.corpus)
    B = V.blocs(a.corpus)
    y = np.load(V.P10 / f"_y-{a.corpus}.npy")
    g = np.load(V.P10 / f"_g-{a.corpus}.npy", allow_pickle=True)
    folds = sorted(set(g.tolist()))
    Xw, yw = _xw_yw()
    print(f"corpus {a.corpus} : {len(y)} lignes Python · {len(yw)} lignes w46 "
          f"({int(yw.sum())} positives) · {len(folds)} plis\n", flush=True)

    res = {}
    t0 = time.time()
    lis("C0  V13 rejoue (labels w46 vrais)", conjoint(B, y, g, folds, yw), D, res)
    print(f"      ({time.time() - t0:.0f} s)", flush=True)

    aucs = []
    for k in range(a.graines):
        rng = np.random.default_rng(9000 + k)
        ypm = yw[rng.permutation(len(yw))]
        p = conjoint(B, y, g, folds, ypm)
        lis(f"C1  w46 labels permutes (graine {9000 + k})", p, D, res)
        aucs.append(res[f"C1  w46 labels permutes (graine {9000 + k})"]["strates"]["aveugle"]["auc"])
    if aucs:
        print(f"\n  C1 sur {len(aucs)} graines : moyenne {np.mean(aucs):.4f} · "
              f"min {min(aucs):.4f} · max {max(aucs):.4f}", flush=True)

    lis("C2  w46 SEUL (zero Python en train)", w46_seul(B, y, g, folds), D, res)

    rap = {"at": datetime.now(UTC).isoformat(), "corpus": a.corpus,
           "fenetre": "governance/act2/window-p14-variance-proposal.md",
           "C": C_FIXE, "n_python": int(len(y)), "n_w46": int(len(yw)),
           "controles": res}
    f = V.OUT / f"transfert-controle-{a.corpus}.json"
    f.write_text(json.dumps(rap, ensure_ascii=False, indent=1))
    print(f"\necrit : {f}\nsha256 : {hashlib.sha256(f.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
