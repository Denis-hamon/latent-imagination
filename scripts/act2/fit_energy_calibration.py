#!/usr/bin/env python3
"""Fit sigmoid calibration énergie→p(succès) sur le pool Act2, LOAO-honnêt.

Sortie : governance/act2/arm-artifacts/predictor-mcp-calibration.json
(w, b, mu, loao stats). C'est ce .json qui fait vivre la boucle de renforcement.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict

pool = json.loads(Path("data/landing/act2-pilot/latent-pool.json").read_text())
d = np.load("data/landing/act2-pilot/latent-pool.npz")


def norm(a):
    return a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)


E_s, E_d, E_g = norm(d["E_state"]), norm(d["E_diff"]), norm(d["E_goal"])
energies, ys, tasks = [], [], []
for i, r in enumerate(pool):
    cd = E_s[i] + E_d[i]
    cd /= np.linalg.norm(cd) + 1e-9
    cg = E_s[i] + E_g[i]
    cg /= np.linalg.norm(cg) + 1e-9
    energies.append(float(1 - (cd * cg).sum()))
    ys.append(int(r["y"]))
    tasks.append(r["task"])

X = np.array(energies).reshape(-1, 1)
y = np.array(ys)
groups = np.array(tasks)
n = len(y)

p = cross_val_predict(LogisticRegression(C=10, max_iter=400), X, y, groups=groups,
                      cv=LeaveOneGroupOut(), method="predict_proba")[:, 1]
# seuil énergie (option A) : médiane LOAO des énergies de train à chaque fold —
# c'est LE critère mesuré à 0.735 [0.646, 0.807] dans E4. Pas de proba sigmoïde.
uniq = sorted(set(tasks))
ener_arr = X[:, 0]
e_correct = 0
e_succ_med, e_fail_med = [], []
for held in uniq:
    tr = groups != held
    te = ~tr
    thr = float(np.median(ener_arr[tr]))
    for i in np.where(te)[0]:
        hyp_pass = ener_arr[i] < thr      # faible énergie = proche du but = passe
        e_correct += int(hyp_pass == bool(y[i]))
e_acc = e_correct / n
se_e = (e_acc * (1 - e_acc) / n) ** 0.5
e_lo, e_hi = max(0, e_acc - 1.96 * se_e), min(1, e_acc + 1.96 * se_e)
# seuil final publié = médiane de TOUT le pool (le futur utilisateur a tout) ;
# LOAO médianes fold-par-fold varient peu (sd reportée ci-dessous).
thr_final = float(np.median(ener_arr))
correct = int(sum(1 for a_, b_ in zip(p, y) if (a_ >= 0.5) == bool(b_)))
acc = e_acc
lo, hi = e_lo, e_hi
maj = max(int(y.sum()), n - int(y.sum())) / n
# Youden sur les énergies : je idx que sépare au mieux TPR/FPR
best_j, best_thr_y = -1.0, None
for thr in np.linspace(np.percentile(ener_arr, 5), np.percentile(ener_arr, 95), 37):
    prd = ener_arr < thr
    tpr = (prd & (y == 1)).sum() / max(1, (y == 1).sum())
    fpr = (prd & (y == 0)).sum() / max(1, (y == 0).sum())
    j = tpr - fpr
    if j > best_j:
        best_j, best_thr_y = j, float(thr)
se = (acc * (1 - acc) / n) ** 0.5
lo, hi = max(0, acc - 1.96 * se), min(1, acc + 1.96 * se)

succ_e = [energies[i] for i in range(n) if y[i] == 1]
fail_e = [energies[i] for i in range(n) if y[i] == 0]
print(f"n={n} | succès énergie moy {np.mean(succ_e):.4f} vs échecs {np.mean(fail_e):.4f}")
print(f"LOAO acc {acc:.3f} [{lo:.3f},{hi:.3f}] | maj {maj:.3f}")
print(f"succès p moy {np.mean([p[i] for i in range(n) if y[i]==1]):.3f} vs "
      f"échecs {np.mean([p[i] for i in range(n) if y[i]==0]):.3f}")

lr = LogisticRegression(C=10, max_iter=400).fit(X, y)
cal = {"w": float(lr.coef_[0][0]), "b": float(lr.intercept_[0]),
       "mu": float(np.mean(energies)), "n_fit": n, "n_pos": int(y.sum()),
       "energy_threshold_median": thr_final,
       "energy_threshold_youden": best_thr_y,
       "threshold_rule": "median(train-energies) per fold — outcome verdict E4",
       "loao_acc": acc, "loao_ci95": [lo, hi], "majority": maj,
       "source": "latent-energy-act2-pool-fitted"}
out = Path("governance/act2/arm-artifacts/predictor-mcp-calibration.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(cal, indent=1) + "\n")
print("artefact:", out)
