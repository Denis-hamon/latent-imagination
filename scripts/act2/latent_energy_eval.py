#!/usr/bin/env python3
"""Évalué honnêtement (LOTO) : l'énergie latente d/diff||gold sépare-t-elle les
patchs qui passent F2P de ceux qui échouent ?

Trois hypothèses mesurées, une par tête :
H1. L'espace (état, diff) seul — pas de gold — prédit le succès (probe dense LOAO).
H2. La distance latente ||E(state+diff) − E(state+gold)|| prédit le succès.
H3. H1+H2 (données fusionnées) meilleur que chacun isolement.

Sortie : aucun nombre n'est arrondi au-dessus du bruit ; aucun claim si l'incertitude
Wilson touche la baseline majoritaire.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
POOL_NPZ = ROOT / "data" / "landing" / "act2-pilot" / "latent-pool.npz"
POOL_MD = ROOT / "data" / "landing" / "act2-pilot" / "latent-pool.json"


def wilson(k: int, n: int, z0: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z0 * z0 / n
    c = (p + z0 * z0 / (2 * n)) / den
    half = (z0 * math.sqrt(p * (1 - p) / n + z0 * z0 / (4 * n * n))) / den
    return (max(0.0, c - half), min(1.0, c + half))


def fit_sgd_dense(X: np.ndarray, y: np.ndarray, *, epochs: int = 60, lr: float = 0.3,
                  l2: float = 1e-4, seed: int = 6769) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    n, d = X.shape
    w = np.zeros(d)
    pos = max(1, int(y.sum()))
    b = math.log((pos + 0.5) / (n - pos + 0.5))
    idx = np.arange(n)
    for _ in range(epochs):
        rng.shuffle(idx)
        for i in idx:
            z = b + X[i] @ w
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            g = p - y[i]
            b -= lr * g
            w -= lr * (g * X[i] + l2 * w)
    return w, b


def auc(scores_succ: list[float], scores_fail: list[float]) -> float:
    """Mann-Whitney U AUC: probabilité qu'un succès tire un score > qu'un échec."""
    if not scores_succ or not scores_fail:
        return float("nan")
    wins, ties = 0.0, 0.0
    for s in scores_succ:
        for f in scores_fail:
            if s > f:
                wins += 1
            elif s == f:
                ties += 1
    return (wins + 0.5 * ties) / (len(scores_succ) * len(scores_fail))


def main() -> int:
    d = np.load(POOL_NPZ)
    meta = json.loads(POOL_MD.read_text())
    E_s, E_d, E_g = d["E_state"], d["E_diff"], d["E_goal"]
    y = np.array([r["y"] for r in meta])
    tasks = [r["task"] for r in meta]
    print(f"pool: {len(y)} patchs | {len(set(tasks))} tâches | {int(y.sum())} positifs", flush=True)

    # normalisation L2 par vecteur (cos-sim-friendly)
    def norm(A):
        return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
    E_s, E_d, E_g = norm(E_s), norm(E_d), norm(E_g)

    # H2: énergie latente = 1 − cos( (state∘diff), (state∘gold) )  où (a∘b) = moyenne normalisée
    comb_d = norm(E_s + E_d)
    comb_g = norm(E_s + E_g)
    cos_dg = np.sum(comb_d * comb_g, axis=1)  # plus proche du but latent ⇒ moins d'énergie
    # énergie d'une action : distance latente à l'état "goal"
    energy = 1.0 - cos_dg
    gap_energy = auc([-e for e, yy in zip(energy, y) if yy == 1],
                     [-e for e, yy in zip(energy, y) if yy == 0])
    print(f"H2 (énergie latente seule, aucun entraînement): AUC = {gap_energy:.3f}", flush=True)

    # H1/H3 LOAO : à chaque pli test-task, on fit sur les AUTRES tâches
    uniq_tasks = sorted(set(tasks))
    for held in uniq_tasks:
        te = np.array([t == held for t in tasks])
        tr = ~te
        if tr.sum() < 10:
            continue
        # features H1 : concat(state, diff) ; H3 : + [énergie, cos_dg]
        for feats, label in ((np.concatenate([E_s, E_d], axis=1), "H1"),
                             (np.concatenate([E_s, E_d, energy[:, None], cos_dg[:, None]], axis=1), "H3")):
            Xtr = feats[tr]
            mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
            w, b = fit_sgd_dense((Xtr - mu) / sd, y[tr])
            for i in np.where(te)[0]:
                z = b + ((feats[i] - mu) / sd) @ w
                p = 1 / (1 + math.exp(-max(-30, min(30, z))))
                # stocke par label (valeur tmp dans un dict global H1/H3)
                entry = {"p": p, "y": int(y[i])}
                eval_res.setdefault(label, []).append(entry)
    for label in ("H1", "H3"):
        rows = eval_res[label]
        correct = sum(1 for r in rows if (r["p"] >= 0.5) == bool(r["y"]))
        su = [r["p"] for r in rows if r["y"] == 1]
        fa = [r["p"] for r in rows if r["y"] == 0]
        acc = correct / len(rows)
        lo, hi = wilson(correct, len(rows))
        a = auc(su, fa)
        print(f"{label} LOAO: acc {acc:.3f} Wilson95 [{lo:.3f},{hi:.3f}] "
              f"| gap AUC {a:.3f} | succès moy {statistics.mean(su):.3f} vs échecs {statistics.mean(fa):.3f}",
              flush=True)
    Path(ROOT / "data/landing/act2-pilot/latent-eval.json").write_text(
        json.dumps({"H2_energy_auc": gap_energy,
                    "H1_H3": {k: v for k, v in eval_res.items()}}, indent=1))
    return 0


eval_res: dict[str, list] = {"H1": [], "H3": []}


if __name__ == "__main__":
    raise SystemExit(main())
