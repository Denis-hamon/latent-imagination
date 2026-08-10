#!/usr/bin/env python3
"""G1 — l'énergie latente survit-elle SANS le gold ?  (gate de production du MCP)

Contexte : l'énergie E4 (AUC 0.817) compare le composite (état+diff) au composite
(état+GOLD). En production il n'y a pas de gold — le MCP ne connaît pas la
destination. Deux stratégies goal-free, LOAO-strictes (tâche entière tenue dehors,
références de retrieval/attracteurs prises uniquement dans le train du fold) :

  R1  but retrievé : j* = argmax_j cos(E_s_i, E_s_j) sur le train (autres tâches) ;
      énergie = 1 − cos(c_d_i, c_g_j*). Variante R3 : moyenne des c_g des 3 voisins.
  F1  failure-attractor : score = d(c_d_i, fail le + proche) − d(c_d_i, pass le +
      proche) — aucune notion de but, pure géométrie du pool.

Contrôles : GOLD (0.817 attendu — reproduction), PERM (buts permutés in-fold ≈ 0.5).
Seuil médiane-train par fold pour les acc, McNemar vs GOLD (apparié).

Sortie : data/landing/act2-pilot/g1-goal-free.json
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


def auc(succ, fail) -> float:
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
    cd = norm(E_s + E_d)
    cg = norm(E_s + E_g)

    scores = {k: np.zeros(n) for k in ("GOLD", "R1", "R3", "F1", "K5V", "PERM")}
    rng = np.random.default_rng(6769)

    for held in sorted(set(tasks)):
        te = tasks == held
        tr = ~te
        ti = np.where(te)[0]
        tri = np.where(tr)[0]
        cg_tr, cd_tr, y_tr = cg[tr], cd[tr], y[tr]

        # R1/R3 : voisins par similarité d'ÉTAT (issue→issue), dans le train seul
        sim_state = E_s[ti] @ E_s[tri].T                       # (|te|, |tr|)
        order = np.argsort(-sim_state, axis=1)
        for r_i, i in enumerate(ti):
            j1 = tri[order[r_i, 0]]
            j3 = tri[order[r_i, :3]]
            scores["R1"][i] = 1.0 - float(cd[i] @ cg[j1])
            m3 = cg[j3].mean(0)
            scores["R3"][i] = 1.0 - float(cd[i] @ (m3 / (np.linalg.norm(m3) + 1e-9)))
            scores["GOLD"][i] = 1.0 - float(cd[i] @ cg[i])
            scores["PERM"][i] = 1.0 - float(cd[i] @ cg_tr[rng.integers(len(tri))])

        # F1 : attracteurs pass/fail du train (distance en cos sur composites)
        if (y_tr == 0).any() and (y_tr == 1).any():
            D_fail = 1.0 - cd[ti] @ cd_tr[y_tr == 0].T
            D_pass = 1.0 - cd[ti] @ cd_tr[y_tr == 1].T
            scores["F1"][ti] = D_fail.min(1) - D_pass.min(1)   # >0 : plus proche du succès
        # K5V : contrôle retrieval vanilla — moyenne des y des 5 composites train les + proches
        sim_cd = cd[ti] @ cd_tr.T
        knn = np.argsort(-sim_cd, axis=1)[:, :5]
        scores["K5V"][ti] = y_tr[knn].mean(1)

    out = {"n": n, "scores": {}, "loao_threshold": {}}
    for k, s in scores.items():
        # pour F1 et K5V "score grand = bien" ; pour les énergies "petit = bien"
        orient = s if k in ("F1", "K5V") else -s
        out["scores"][k] = {"auc": auc(orient[y == 1].tolist(), orient[y == 0].tolist())}
        # acc par seuil médiane-train par fold
        preds = np.zeros(n, dtype=int)
        for held in sorted(set(tasks)):
            te = tasks == held
            tr = ~te
            thr = np.median(orient[tr]) if k != "F1" else np.median(orient[tr])
            preds[te] = (orient[te] > thr).astype(int)
        kc = int((preds == y).sum())
        lo, hi = wilson(kc, n)
        out["loao_threshold"][k] = {"acc": kc / n, "wilson95": [lo, hi]}
        out["scores"][k][f"preds"] = preds.tolist()

    # complémentarité F1 × GOLD : Spearman + AUC du rang moyen
    def rankdata(a):
        order = np.argsort(a, kind="mergesort")
        r = np.empty(len(a))
        i = 0
        while i < len(a):
            j = i
            while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
                j += 1
            r[order[i:j + 1]] = (i + j) / 2.0 + 1.0
            i = j + 1
        return r
    rho = float(np.corrcoef(rankdata(-scores["GOLD"]), rankdata(scores["F1"]))[0, 1])
    combo = (rankdata(-scores["GOLD"]) + rankdata(scores["F1"])) / 2
    out["combo_GOLD_F1"] = {"spearman": rho,
                            "auc": auc(combo[y == 1].tolist(), combo[y == 0].tolist())}

    # McNemar GOLD vs chaque stratégie goal-free
    from math import comb
    pred_g = np.array(out["scores"]["GOLD"]["preds"]) == y
    out["mcnemar_vs_gold"] = {}
    for k in ("R1", "R3", "F1"):
        pred_k = np.array(out["scores"][k]["preds"]) == y
        b = int((pred_g & ~pred_k).sum())
        c = int((~pred_g & pred_k).sum())
        n_disc = b + c
        p = (2 * min(sum(comb(n_disc, i) for i in range(0, min(b, c) + 1)),
                     sum(comb(n_disc, i) for i in range(max(b, c), n_disc + 1)))
             / 2 ** n_disc) if n_disc else 1.0
        out["mcnemar_vs_gold"][k] = {"b_gold_only": b, "c_free_only": c, "p_exact": min(1.0, p)}

    maj = max(int(y.sum()), int((1 - y).sum())) / n
    out["majority"] = maj
    print(f"\n===== G1 — énergie goal-free, n={n} (majorité {maj:.3f}) =====")
    print(f"{'score':6s} | {'AUC':6s} | acc LOAO (seuil médiane)")
    for k in ("GOLD", "R1", "R3", "F1", "K5V", "PERM"):
        t = out["loao_threshold"][k]
        print(f"{k:6s} | {out['scores'][k]['auc']:.3f} | {t['acc']:.3f} "
              f"[{t['wilson95'][0]:.3f},{t['wilson95'][1]:.3f}]")
    print("McNemar vs GOLD :", json.dumps(out["mcnemar_vs_gold"]))
    print(f"Spearman(GOLD, F1) = {out['combo_GOLD_F1']['spearman']:+.3f} | "
          f"AUC rang-moyen GOLD+F1 = {out['combo_GOLD_F1']['auc']:.3f}")

    for k in out["scores"]:
        out["scores"][k].pop("preds")
    (PILOT / "g1-goal-free.json").write_text(json.dumps(out, indent=1))
    print(f"\nartefact : {PILOT / 'g1-goal-free.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
