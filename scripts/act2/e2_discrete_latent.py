#!/usr/bin/env python3
"""E2 — latent Bernoulli du verdict vs z gaussien (LeCun §4.2 contre Var-JEPA).

Question : à architecture et protocole identiques, est-ce que discrétiser la
représentation latente (z binaire, style LeCun) détruit, conserve ou améliore le
signal verdict, par rapport au latent continu (régime gaussien implicite) ?

Contrôle strict — tout est commun aux trois bras :
  - même encodeur gelé (uniXCoder, embeddings déjà dans latent-pool.npz)
  - même composition : c = E_state + E_action
  - même règle de seuil : médiane des énergies du TRAIN, recalculée à chaque fold
  - même LOAO : une tâche entière tenue dehors à chaque fold (69 folds)

Bras :
  A. continu  : énergie = 1 − cos(norm(c_d), norm(c_g))   [contrôle = verdict E4]
  B. Bernoulli 1-bit : z = 1[c > médiane_train(dim)], énergie = Hamming/768
     (MAP déterministe du z ~ Bernoulli de LeCun ; version stochastique omise
     volontairement — le bruit d'échantillonnage n'ajoute pas d'information,
     il teste la variance, pas la discrétude)
  C. 2-bit : quartiles train par dim, énergie = |q_d − q_g|.mean()/3

Les seuils de quantification sont appris sur le train SEUL à chaque fold — pas de fuite.
Sortie : data/landing/act2-pilot/e2-discrete-eval.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"


def norm(A: np.ndarray) -> np.ndarray:
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def wilson(k: int, n: int) -> tuple[float, float]:
    z = 1.96
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return max(0.0, c - h), min(1.0, c + h)


def auc(succ: list[float], fail: list[float]) -> float:
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


def energies(train_idx, cd, cg, mode):
    """Énergie par échantillon selon le bras. Retourne (E_train, E_all)."""
    if mode == "cont":
        E = 1.0 - (cd * cg).sum(-1)
    elif mode == "bit1":
        med_d = np.median(cd[train_idx], axis=0)
        med_g = np.median(cg[train_idx], axis=0)
        z_d = (cd > med_d).astype(np.int8)
        z_g = (cg > med_g).astype(np.int8)
        E = (z_d != z_g).mean(-1)
    elif mode == "bit2":
        q_d = np.quantile(cd[train_idx], [0.25, 0.5, 0.75], axis=0)  # (3, 768)
        q_g = np.quantile(cg[train_idx], [0.25, 0.5, 0.75], axis=0)
        # digitize par dim : quartiles lus le long de l'axe 0
        c_d = np.stack([np.searchsorted(q_d[:, j], cd[:, j]) for j in range(cd.shape[1])], axis=1)
        c_g = np.stack([np.searchsorted(q_g[:, j], cg[:, j]) for j in range(cg.shape[1])], axis=1)
        E = np.abs(c_d - c_g).mean(-1) / 3.0
    else:
        raise ValueError(mode)
    return E[train_idx], E


def main() -> int:
    rows = json.loads((PILOT / "latent-pool.json").read_text())
    d = np.load(PILOT / "latent-pool.npz")
    # pré-normalisation par embedding PUIS composition — recette canonique E4
    # (fit_energy_calibration.py) ; sans elle le contrôle ne reproduit pas 0.735
    E_s, E_d, E_g = norm(d["E_state"]), norm(d["E_diff"]), norm(d["E_goal"])
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    assert E_s.shape[0] == len(rows)

    # composition identique aux trois bras (normée pour le continu seulement ;
    # les bras discrets apprennent leurs propres échelles via les médianes)
    cd_raw, cg_raw = E_s + E_d, E_s + E_g
    cd_n, cg_n = norm(cd_raw), norm(cg_raw)

    uniq = sorted(set(tasks.tolist()))
    res = {m: {"preds": [], "energies": [], "ys": []} for m in ("cont", "bit1", "bit2")}
    for held in uniq:
        te = tasks == held
        tr = np.where(~te)[0]
        if tr.sum() < 20:
            continue
        for mode, (a, b) in (("cont", (cd_n, cg_n)), ("bit1", (cd_raw, cg_raw)),
                             ("bit2", (cd_raw, cg_raw))):
            E_tr, E_all = energies(tr, a, b, mode)
            thr = np.median(E_tr)  # règle E4 : un seul hyperparam, appris sur train
            idx = np.where(te)[0]
            res[mode]["preds"].extend((E_all[idx] < thr).astype(int).tolist())
            res[mode]["energies"].extend(E_all[idx].tolist())
            res[mode]["ys"].extend(y[idx].tolist())

    out = {"n_folds": len(res["cont"]["ys"]), "branches": {}}
    for mode, r in res.items():
        ys, ps = np.array(r["ys"]), np.array(r["preds"])
        es = np.array(r["energies"])
        k = int((ps == ys).sum())
        n = len(ys)
        lo, hi = wilson(k, n)
        succ = (-es[ys == 1]).tolist()  # énergie basse = succès → score = −E
        fail = (-es[ys == 0]).tolist()
        out["branches"][mode] = {
            "acc": k / n, "wilson95": [lo, hi], "auc": auc(succ, fail),
            "mean_energy_succ": float(es[ys == 1].mean()),
            "mean_energy_fail": float(es[ys == 0].mean()),
        }

    # McNemar apparié : bras discret vs contrôle continu (mêmes folds, mêmes seuils)
    ys = np.array(res["cont"]["ys"])
    for mode in ("bit1", "bit2"):
        ok_c = np.array(res["cont"]["preds"]) == ys
        ok_d = np.array(res[mode]["preds"]) == ys
        b = int((ok_c & ~ok_d).sum())   # continu seul correct
        c = int((~ok_c & ok_d).sum())   # discret seul correct
        # p exact binomial sur les paires discordantes
        from math import comb
        n_disc = b + c
        pval = (2 * min(sum(comb(n_disc, i) for i in range(0, min(b, c) + 1)),
                        sum(comb(n_disc, i) for i in range(max(b, c), n_disc + 1)))
                / 2 ** n_disc) if n_disc else 1.0
        out["branches"][mode]["mcnemar_vs_cont"] = {"b_cont_only": b, "c_disc_only": c,
                                                    "p_exact": min(1.0, pval)}

    maj = max(int(ys.sum()), int((1 - ys).sum())) / len(ys)
    out["majority_baseline"] = maj

    print(f"\n===== E2 — discret vs gaussien, n={out['n_folds']} (majorité {maj:.3f}) =====")
    for mode, m in out["branches"].items():
        mc = m.get("mcnemar_vs_cont")
        print(f"{mode:5s} | acc {m['acc']:.3f} [{m['wilson95'][0]:.3f},{m['wilson95'][1]:.3f}]"
              f" | AUC {m['auc']:.3f} | E_succ {m['mean_energy_succ']:.4f}"
              f" vs E_fail {m['mean_energy_fail']:.4f}"
              + (f" | McNemar b={mc['b_cont_only']} c={mc['c_disc_only']} p={mc['p_exact']:.3f}" if mc else ""))

    (PILOT / "e2-discrete-eval.json").write_text(json.dumps(out, indent=1))
    print(f"\nartefact : {PILOT / 'e2-discrete-eval.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
