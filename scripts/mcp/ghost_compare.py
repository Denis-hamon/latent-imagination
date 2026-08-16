#!/usr/bin/env python3
"""Ghost v0.7.0 (pivot PR Simulator) — machinerie PURE de world.compare_patches.

Contrat produit (dérivé de la démo pré-enregistrée 15.4, règle mesurée :
n >= 8 exécutions réelles pour recommander, sinon abstention) :
  Phase 1 (issues < n_min) : sélection informative (prior goal-free sur le
    pool servi + greedy spread) => plan d'exécution pour le caller ;
    AUCUNE recommandation (le fallback-prior ne recommande pas — leçon 15.4).
  Phase 2 (issues >= n_min) : calibration locale (logreg ridge sur features
    pool∪issues, conforme LOO, α=0.10) => recommandation + probabilités +
    abstentions + disclosures.
Toute l'exécution réelle des tests appartient au caller (grounded_by déclaré
dans les issues) — Ghost ne devine jamais une issue.
"""
from __future__ import annotations

import math


def goal_free_scores(cd_prior, y_prior, tasks_prior, E_cand, s11) -> list[float]:
    """Scores LOAO-F1 des candidats contre le pool servi (propre candidat
    exclu des voisins) — la perception prior du world model."""
    import numpy as np
    n_prior = len(y_prior)
    allm = np.vstack([cd_prior, E_cand])
    task_ids = np.concatenate([tasks_prior, np.array([f"__cand_{i}" for i in range(len(E_cand))])])
    y_all = np.concatenate([y_prior, np.zeros(len(E_cand))])
    f1 = s11._loao_f1_features(allm, task_ids, y_all)
    return [float(v) for v in f1[n_prior:]]


def informative_selection(ids: list[str], scores: list[float], n: int) -> list[str]:
    """n candidats informatifs, déterministe : ancre médiane + greedy spread
    (validé par la démo pré-enregistrée 1babd393, mêmes règles)."""
    if n >= len(ids):
        return list(ids)
    order = sorted(range(len(ids)), key=lambda i: (scores[i], ids[i]))
    sel = [order[len(order) // 2]]
    rest = [i for i in order if i not in sel]
    while len(sel) < n and rest:
        rest.sort(key=lambda i: min(abs(scores[i] - scores[s]) for s in sel), reverse=True)
        sel.append(rest.pop(0))
    return [ids[i] for i in sel]


def conformal_quantile(errs: list[float], alpha: float) -> float | None:
    n = len(errs)
    if n < 4:
        return None
    q = math.ceil((1 - alpha) * (n + 1)) - 1
    q = max(0, min(n - 1, q))
    return float(sorted(errs)[q])


def calibrate_local(E_pool, y_pool, E_issues: dict,
                    y_issues: dict, E_cand, ids: list[str], s11,
                    alpha: float = 0.10, n_min: int = 8) -> dict:
    """Calibration locale (Phase 2). Retourne le contrat produit complet."""
    import numpy as np
    n_local = len(y_issues)
    if n_local < n_min:
        return {"regime": "fallback-prior", "n_local": n_local, "n_min": n_min,
                "disclosure": (f"n={n_local} < {n_min} : calibration locale impossible — "
                               "AUCUNE recommandation émise ; exécutez plus de tests réels "
                               "(plan fourni par la phase 1) ; jamais de prédiction devinée.")}
    # issues locaux ordonnés déterministiquement
    local_ids = sorted(y_issues.keys())
    Xl = np.vstack([E_issues[i] for i in local_ids])
    yl = np.array([int(y_issues[i]) for i in local_ids])
    if len(set(yl.tolist())) < 2:
        return {"regime": "degenerate-local", "n_local": n_local, "n_min": n_min,
                "disclosure": "toutes les issues locales ont la même classe — calibration "
                              "impossible, aucune recommandation."}
    w = s11.logreg_fit(Xl, yl, lam=1.0, iters=300)
    Xb = np.column_stack([np.ones(len(E_cand)), E_cand])
    p_all = 1.0 / (1.0 + np.exp(-(Xb @ w)))
    Xlb = np.column_stack([np.ones(n_local), Xl])
    p_cal = 1.0 / (1.0 + np.exp(-(Xlb @ w)))
    errs = [abs(float(y) - float(p)) for y, p in zip(yl, p_cal)]
    # résidus LOO honnêtes (leave-one-out), pas in-sample
    loo_errs = []
    idx = np.arange(n_local)
    for i in idx:
        tr = idx[idx != i]
        if len(set(yl[tr].tolist())) < 2:
            loo_errs.append(errs[i])  # fold dégénéré : résidu in-sample (divulgué)
            continue
        wi = s11.logreg_fit(Xl[tr], yl[tr], lam=1.0, iters=300)
        xi = np.concatenate([[1.0], Xl[i]])
        pi = float(1.0 / (1.0 + np.exp(-(xi @ wi))))
        loo_errs.append(abs(float(yl[i]) - pi))
    tau = conformal_quantile(loo_errs, alpha)
    out = {"regime": "local", "n_local": n_local, "n_min": n_min,
           "alpha": alpha, "tau": tau,
           "loo_folds_degenerate": int(sum(1 for i in idx
                                           if len(set(yl[idx[idx != i]].tolist())) < 2)),
           "candidates": []}
    for i, cid in enumerate(ids):
        resid = abs(float(p_all[i]) - 0.5) * 2.0
        abst = tau is not None and resid < tau and cid not in y_issues
        out["candidates"].append({
            "id": cid, "p_success": round(float(p_all[i]), 4),
            "measured": cid in y_issues,
            "measured_y": y_issues.get(cid),
            "abstained": bool(abst)})
    measured_rank = [c for c in out["candidates"] if c["measured"] and c["measured_y"] == 1]
    unmeasured = [c for c in out["candidates"] if not c["measured"] and not c["abstained"]]
    rec_pool = measured_rank + sorted(unmeasured, key=lambda c: -c["p_success"])
    out["recommendation"] = ({"id": rec_pool[0]["id"],
                              "p_success": rec_pool[0]["p_success"],
                              "basis": "issue mesurée y=1" if measured_rank else "p_success max hors abstention"}
                             if rec_pool else None)
    if not out["recommendation"]:
        out["disclosure"] = "aucun candidat recommandable (tous abstention ou mesurés négatifs)"
    return out
