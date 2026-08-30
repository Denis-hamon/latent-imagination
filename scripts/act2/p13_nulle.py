#!/usr/bin/env python3
"""P13 — nulle du MAXIMUM sur K variantes. Fenêtre `window-p13-scamper-proposal.md`.

ZÉRO appel LLM. La barre à franchir n'est ni 0,50 ni la nulle d'une variante
isolée : on essaie K variantes sur 121 paires dont les labels ont été vus, et le
meilleur de K tirages passe pour un résultat si on ne corrige pas.

À chaque permutation intra-instance (le taux de positifs de chaque instance est
conservé), les K variantes sont REFITTÉES en LOO complet et l'on retient le
maximum de leurs AUC⊥. La barre est le 95e centile de cette distribution.

Le pair-set est RECALCULÉ à chaque permutation : la strate aveugle est définie
par les labels, elle bouge donc avec eux. Réutiliser le pair-set observé
mesurerait une autre quantité que celle qu'on rapporte.

Usage :
  .venv/bin/python scripts/act2/p13_nulle.py --corpus p12 --variantes V1,V2,V3,V4,V5,V6 --perms 200
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "act2"))
AP = ROOT / "data" / "landing" / "act2-pilot"
P10 = AP / "night-harvest" / "py-p12" / "p10"
OUT = AP / "night-harvest" / "py-p12" / "p13"
_W: dict = {}


def _init(corpus, vids):
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[v] = "1"
    import p13_metrics as M
    import p13_variants as V
    _W.update(M=M, V=V, corpus=corpus, vids=vids,
              B=V.blocs(corpus), D=M.charge(corpus),
              y=np.load(P10 / f"_y-{corpus}.npy"),
              g=np.load(P10 / f"_g-{corpus}.npy", allow_pickle=True))
    _W["folds"] = sorted(set(_W["g"].tolist()))


def _task(graine):
    M, V, D = _W["M"], _W["V"], _W["D"]
    rng = np.random.default_rng(graine)
    yy = M.permute_intra(_W["y"], D["inst"], rng)
    pr = M.paires(yy, D["inst"], D["per"], D["test"], D["key"], "aveugle")
    if not len(pr):
        return None
    out = {}
    for vid in _W["vids"]:
        p = V.VARIANTES[vid][1](_W["B"], yy, _W["g"], _W["folds"])
        out[vid] = M.auc_paires(p, pr)[0]
    return {"graine": graine, "n_paires": int(len(pr)), "par_variante": out,
            "max": float(np.nanmax(list(out.values())))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=("w46", "p12"), default="p12")
    ap.add_argument("--variantes", required=True)
    ap.add_argument("--perms", type=int, default=200)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    vids = [v.strip() for v in a.variantes.split(",") if v.strip()]
    K_DECLARE = 13   # taille de la liste GELÉE par la fenêtre, pas du sous-ensemble joué

    res = []
    with cf.ProcessPoolExecutor(max_workers=a.workers, initializer=_init,
                                initargs=(a.corpus, vids)) as ex:
        for i, r in enumerate(ex.map(_task, [7000 + k for k in range(a.perms)]), 1):
            if r:
                res.append(r)
            if i % 10 == 0:
                m = np.array([x["max"] for x in res])
                print(f"  {i}/{a.perms} · max courant : moyenne {m.mean():.4f} "
                      f"p95 {np.percentile(m, 95):.4f}", flush=True)
                # checkpoint : ces runs durent des heures et ont ete tues plusieurs
                # fois aujourd'hui ; sans reprise on repart de zero a chaque fois.
                (OUT / f"nulle-partielle-{a.corpus}.json").write_text(
                    json.dumps({"n": len(res), "tirages": res}, ensure_ascii=False))

    mx = np.array([r["max"] for r in res])
    par = {v: np.array([r["par_variante"][v] for r in res]) for v in vids}
    # barre conservatrice de Bonferroni sur la liste GELÉE (K=13), calculée sur
    # la nulle de la variante isolée la plus dispersée : elle ignore la
    # corrélation entre variantes, donc elle est PLUS HAUTE que la barre exacte.
    iso = max(vids, key=lambda v: float(np.nanstd(par[v])))
    bonf = float(np.nanpercentile(par[iso], 100 * (1 - 0.05 / K_DECLARE)))
    rap = {"at": datetime.now(UTC).isoformat(), "corpus": a.corpus,
           "fenetre": "governance/act2/window-p13-scamper-proposal.md",
           "n_permutations": len(res), "variantes_jouees": vids,
           "K_gele_par_la_fenetre": K_DECLARE,
           "barre_exacte_du_max_p95": round(float(np.percentile(mx, 95)), 4),
           "max_du_max": round(float(mx.max()), 4),
           "nulle_du_max_moyenne": round(float(mx.mean()), 4),
           "barre_bonferroni_conservatrice": round(bonf, 4),
           "variante_de_reference_bonferroni": iso,
           "par_variante": {v: {"moyenne": round(float(np.nanmean(par[v])), 4),
                                "ecart_type": round(float(np.nanstd(par[v], ddof=1)), 4),
                                "p95": round(float(np.nanpercentile(par[v], 95)), 4),
                                "max": round(float(np.nanmax(par[v])), 4)} for v in vids},
           "tirages": res}
    f = OUT / f"nulle-du-max-{a.corpus}.json"
    f.write_text(json.dumps(rap, ensure_ascii=False, indent=1))
    print(f"\nnulle du MAX sur {len(res)} permutations, {len(vids)} variantes jouées")
    for v in vids:
        d = rap["par_variante"][v]
        print(f"  {v:4s} nulle {d['moyenne']:.4f} ± {d['ecart_type']:.4f}  p95 {d['p95']:.4f}  max {d['max']:.4f}")
    print(f"\n  BARRE EXACTE DU MAX (p95)      : {rap['barre_exacte_du_max_p95']:.4f}")
    print(f"  barre Bonferroni K=13 (conserv.) : {rap['barre_bonferroni_conservatrice']:.4f}")
    print(f"\nécrit : {f}\nsha256 : {hashlib.sha256(f.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
