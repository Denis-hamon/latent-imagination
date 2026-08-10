#!/usr/bin/env python3
"""S1 — prédiction sélective : l'instrument a-t-il un régime haute-confiance ?

Question (Var-JEPA : sélectionner les 50 % les plus confiants → +7 pts) : en
abstenant les décisions proches du seuil, l'exactitude couverte atteint-elle
un niveau déployable (≥0.85) ?

Protocole LOAO-strict, tout recalculé par fold (seuil médiane-train, confiance =
|score − seuil|) — la couverture est décidée globalement APRÈS assignation des
confiances hors-pli (chaque point a un score et une confiance obtenus sans voir
sa tâche). Deux axes mesurés :
  GOLD : énergie E = 1−cos(norm(E_s+E_d), norm(E_s+E_g))  (0.817 connu)
  F1   : répulsion d'échecs goal-free (0.709 connu)

Sortie : data/landing/act2-pilot/s1-selective.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"


def norm(A):
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def wilson(k, n):
    z = 1.96
    p = k / max(1, n)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return max(0.0, c - h), min(1.0, c + h)


def auc(succ, fail):
    if not succ or not fail:
        return float("nan")
    w = t = 0.0
    for a in succ:
        for b in fail:
            if a > b:
                w += 1
            elif a == b:
                t += 1
    return (w + 0.5 * t) / (len(succ) * len(fail))


def main() -> int:
    rows = json.loads((PILOT / "latent-pool.json").read_text())
    d = np.load(PILOT / "latent-pool.npz")
    E_s, E_d, E_g = norm(d["E_state"]), norm(d["E_diff"]), norm(d["E_goal"])
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    n = len(rows)
    cd, cg = norm(E_s + E_d), norm(E_s + E_g)
    energy = 1.0 - (cd * cg).sum(-1)

    uniq = sorted(set(tasks))
    recs = {"GOLD": np.zeros((n, 3)), "F1": np.zeros((n, 3))}  # score_orienté, conf, idx
    for held in uniq:
        te = tasks == held
        tr = ~te
        ti = np.where(te)[0]
        # axe GOLD
        thr = np.median(energy[tr])
        recs["GOLD"][ti, 0] = -energy[ti]              # orienté : haut = succès
        recs["GOLD"][ti, 1] = np.abs(energy[ti] - thr)  # confiance = marge au seuil
        # axe F1 (attracteurs train-only)
        cd_tr, y_tr = cd[tr], y[tr]
        sims = cd[ti] @ cd_tr.T
        d_fail = 1 - sims[:, y_tr == 0]
        d_pass = 1 - sims[:, y_tr == 1]
        f1 = d_fail.min(1) - d_pass.min(1)              # haut = proche succès
        # seuil médiane-train de F1 (appliqué aux points train eux-mêmes)
        f1_tr = (1 - cd_tr @ cd_tr[y_tr == 0].T).min(1) - (1 - cd_tr @ cd_tr[y_tr == 1].T).min(1)
        thr_f = np.median(f1_tr)
        recs["F1"][ti, 0] = f1
        recs["F1"][ti, 1] = np.abs(f1 - thr_f)
        recs["GOLD"][ti, 2] = recs["F1"][ti, 2] = 1

    out = {"n": n, "axes": {}}
    for ax, R in recs.items():
        score, conf = R[:, 0], R[:, 1]
        thr_global = 0.0 if ax == "GOLD" else 0.0  # seuil déjà orienté par-fold: via signe
        pred = np.zeros(n, dtype=int)
        # reconstruction des prédictions par fold (seuils médiane-train déjà utilisés)
        for held in uniq:
            te = tasks == held
            tr = ~te
            thr = np.median((-score)[tr] if ax == "GOLD" else score[tr])
            if ax == "GOLD":
                pred[te] = ((-score)[te] < thr).astype(int)
            else:
                pred[te] = (score[te] > thr).astype(int)
        curve = []
        order = np.argsort(-conf)  # plus confiant d'abord
        for cov in (1.0, 0.75, 0.5, 0.25, 0.10):
            m = max(1, int(round(n * cov)))
            sel = order[:m]
            k = int((pred[sel] == y[sel]).sum())
            lo, hi = wilson(k, m)
            curve.append({"coverage": cov, "n": m, "acc": k / m,
                          "wilson95": [lo, hi],
                          "auc": auc(score[sel][y[sel] == 1].tolist(),
                                     score[sel][y[sel] == 0].tolist())})
        out["axes"][ax] = {"curve": curve,
                           "acc_full": curve[0]["acc"], "auc_full": curve[0]["auc"]}

    print(f"\n===== S1 — prédiction sélective LOAO, n={n} (majorité "
          f"{max(y.mean(), 1-y.mean()):.3f}) =====")
    for ax, a in out["axes"].items():
        print(f"\n{ax} (full acc {a['acc_full']:.3f} / AUC {a['auc_full']:.3f})")
        for c in a["curve"]:
            print(f"  couverture {c['coverage']:4.0%} | n={c['n']:3d} | acc {c['acc']:.3f} "
                  f"[{c['wilson95'][0]:.3f},{c['wilson95'][1]:.3f}] | AUC {c['auc']:.3f}")

    (PILOT / "s1-selective.json").write_text(json.dumps(out, indent=1))
    print(f"\nartefact : {PILOT / 's1-selective.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
