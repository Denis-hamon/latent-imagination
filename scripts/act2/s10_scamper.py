#!/usr/bin/env python3
"""S10 — balayage SCAMPER des variantes du modèle (toutes numpy, 0 call galere).

Protocole commun — LOAO strict par tâche, seuil médiane-train par fold,
marge brute comme confiance (sauf GxF : proba logreg λ=1) ; métriques :
AUC, acc100, cov@≥0.95 (acc≥0.95 ET borne basse Wilson > majorité).
Contrôle positif obligatoire : la variante "champion" DOIT reproduire
uxc GOLD+marge = AUC 0.822 / acc 0.779 / cov 20 % sur v6.

Variantes (lettre SCAMPER) :
  E1  diff→gold seul (sans état)          [Eliminate]
  E2  état→gold seul (sans diff)          [Eliminate — témoin de bruit]
  M1  all-but-the-top : −k premières PC   [Modify/Adapt, k=1,3,8]
  C1  multi-espaces GxF étendu (uxc+Qwen) [Combine, logreg λ=1]
  R1  temporel : train frozen32 → test extension-128 [Reverse/distribution]

Sortie : data/landing/act2-pilot/s10-scamper.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
COVERAGES = (1.0, 0.5, 0.3, 0.25, 0.2, 0.1)
TARGET = 0.95


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
    if not len(succ) or not len(fail):
        return float("nan")
    d = succ[:, None] - fail[None, :]
    return float((np.sum(d > 0) + 0.5 * np.sum(d == 0)) / d.size)


def logreg_fit(X, y, lam=1.0, iters=200):
    Xb = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(Xb.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(Xb @ w)))
        g = Xb.T @ (p - y) + lam * w
        W = p * (1 - p) + 1e-9
        H = (Xb * W[:, None]).T @ Xb + lam * np.eye(Xb.shape[1])
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def loao_energy(cd, cg, y, tasks):
    """Énergie 1−<cd,cg> + marge au seuil médiane-train, LOAO."""
    n = len(y)
    energy = 1.0 - (cd * cg).sum(-1)
    pred = np.zeros(n, int)
    conf = np.zeros(n)
    for held in sorted(set(tasks)):
        te = tasks == held
        thr = np.median(energy[~te])
        pred[te] = (energy[te] < thr).astype(int)
        conf[te] = np.abs(energy[te] - thr)
    return pred, conf, -energy


def gxf_loao(cd, cg, y, tasks, extra=None):
    """GxF : [−energy, F1] (+colonnes extra) logreg λ=1 par fold."""
    n = len(y)
    energy = 1.0 - (cd * cg).sum(-1)
    pred = np.zeros(n, int)
    conf = np.zeros(n)
    sco = np.zeros(n)
    for held in sorted(set(tasks)):
        te, tr = tasks == held, tasks != held
        y_tr = y[tr]
        cd_tr = cd[tr]
        sims = cd[te] @ cd_tr.T
        f1_te = (1 - sims[:, y_tr == 0]).min(1) - (1 - sims[:, y_tr == 1]).min(1)
        f1_tr = ((1 - cd_tr @ cd_tr[y_tr == 0].T).min(1)
                 - (1 - cd_tr @ cd_tr[y_tr == 1].T).min(1))
        Ftr = np.column_stack([-energy[tr], f1_tr] + [e[tr] for e in (extra or [])])
        Fte = np.column_stack([-energy[te], f1_te] + [e[te] for e in (extra or [])])
        mu, sd = Ftr.mean(0), Ftr.std(0) + 1e-9
        w = logreg_fit((Ftr - mu) / sd, y_tr)
        Xte = np.column_stack([np.ones(te.sum()), (Fte - mu) / sd])
        p = 1.0 / (1.0 + np.exp(-(Xte @ w)))
        pred[te] = (p > 0.5).astype(int)
        conf[te] = np.abs(p - 0.5)
        sco[te] = p
    return pred, conf, sco


def report(name, pred, conf, sco, y, maj):
    n = len(y)
    curve = []
    best = 0.0
    order = np.argsort(-conf)
    for cov in COVERAGES:
        m = max(1, int(round(n * cov)))
        sel = order[:m]
        k = int((pred[sel] == y[sel]).sum())
        lo, hi = wilson(k, m)
        curve.append({"coverage": cov, "n": m, "acc": k / m,
                      "wilson95": [lo, hi]})
        if k / m >= TARGET and lo > maj:
            best = max(best, cov)
    res = {"auc": auc(sco[y == 1], sco[y == 0]), "acc100": curve[0]["acc"],
           "max_cov": best, "curve": curve}
    print(f"{name:<38} AUC {res['auc']:.3f} | acc100 {res['acc100']:.3f} "
          f"| cov@≥0.95 {best:4.0%}")
    return res


def main() -> int:
    rows = json.loads((PILOT / "latent-pool-v6.json").read_text())
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    camps = np.array([r.get("campaign", "?") for r in rows])
    n = len(rows)
    maj = max(y.mean(), 1 - y.mean())

    du = np.load(PILOT / "latent-pool-v6.npz")            # uxc (champion)
    dq = np.load(PILOT / "latent-pool-Qwen2.5-Coder-7B-Instruct-last.npz")

    EU = {k: norm(du[k]) for k in ("E_state", "E_diff", "E_goal")}
    EQ = {k: norm(dq[k]) for k in ("E_state", "E_diff", "E_goal")}

    out = {"n": n, "majority": float(maj), "variants": {}}

    # --- contrôle positif : champion v6 ---
    cd, cg = norm(EU["E_state"] + EU["E_diff"]), norm(EU["E_state"] + EU["E_goal"])
    pred, conf, sco = loao_energy(cd, cg, y, tasks)
    ctrl = report("CTRL uxc GOLD+marge (=S7)", pred, conf, sco, y, maj)
    ok = abs(ctrl["auc"] - 0.822) < 0.01 and abs(ctrl["acc100"] - 0.779) < 0.005
    print(f"  → contrôle {'OK' if ok else 'DÉRIVE — STOP'}")
    out["positive_control"] = {"expected": [0.822, 0.779],
                               "got": [ctrl["auc"], ctrl["acc100"]], "ok": ok}
    if not ok:
        return 1
    out["variants"]["ctrl_uxc_gold"] = ctrl

    # --- E1/E2 : ablations dures ---
    cd_d = norm(EU["E_diff"])
    cg_d = norm(EU["E_goal"])
    pred, conf, sco = loao_energy(cd_d, cg_d, y, tasks)
    out["variants"]["E1_diff_seul"] = report("E1 diff→gold (sans état)", pred, conf, sco, y, maj)
    pred, conf, sco = loao_energy(norm(EU["E_state"]), cg_d, y, tasks)
    out["variants"]["E2_etat_seul"] = report("E2 état→gold (sans diff)", pred, conf, sco, y, maj)

    # --- M1 : all-but-the-top (retirer les k premières PC, stats train-fold) ---
    for k_pc in (1, 3, 8):
        pred = np.zeros(n, int); conf = np.zeros(n, ); sco = np.zeros(n)
        for held in sorted(set(tasks)):
            te, tr = tasks == held, tasks != held
            S = np.vstack([EU["E_state"][tr], EU["E_diff"][tr], EU["E_goal"][tr]])
            mu = S.mean(0)
            U = np.linalg.svd(S - mu, full_matrices=False)[2].T
            Vp = U[:, k_pc:]                                  # sous-espace gardé
            def proj(A):
                return (A - mu) @ Vp
            E_s, E_d, E_g = proj(EU["E_state"]), proj(EU["E_diff"]), proj(EU["E_goal"])
            E_sn, E_dn, E_gn = norm(E_s), norm(E_d), norm(E_g)
            cdf = norm(E_sn + E_dn)
            cgf = norm(E_sn + E_gn)
            en = 1 - (cdf * cgf).sum(-1)
            thr = np.median(en[tr])
            pred[te] = (en[te] < thr).astype(int)
            conf[te] = np.abs(en[te] - thr)
            sco[te] = -en[te]
        out["variants"][f"M1_abt_top{k_pc}"] = report(
            f"M1 all-but-the-top k={k_pc}", pred, conf, sco, y, maj)

    # --- C1 : GxF étendu 4 espaces [uxc-ε, uxc-F1, Q-ε, Q-F1] ---
    # (deux passes : cdU pour F1 uxc, cdQ pour F1 qwen ; énergies des deux)
    pred = np.zeros(n, int); conf = np.zeros(n); sco = np.zeros(n)
    eU = 1 - (cd * cg).sum(-1)
    cdQ, cgQ = norm(EQ["E_state"] + EQ["E_diff"]), norm(EQ["E_state"] + EQ["E_goal"])
    eQ = 1 - (cdQ * cgQ).sum(-1)
    for held in sorted(set(tasks)):
        te, tr = tasks == held, tasks != held
        y_tr = y[tr]
        def f1s(cdS):
            sims = cdS[te] @ cdS[tr].T
            f1_te = (1 - sims[:, y_tr == 0]).min(1) - (1 - sims[:, y_tr == 1]).min(1)
            f1_tr = ((1 - cdS[tr] @ cdS[tr][y_tr == 0].T).min(1)
                     - (1 - cdS[tr] @ cdS[tr][y_tr == 1].T).min(1))
            return f1_tr, f1_te
        f1U_tr, f1U_te = f1s(cd)
        f1Q_tr, f1Q_te = f1s(cdQ)
        Ftr = np.column_stack([-eU[tr], f1U_tr, -eQ[tr], f1Q_tr])
        Fte = np.column_stack([-eU[te], f1U_te, -eQ[te], f1Q_te])
        mu, sd = Ftr.mean(0), Ftr.std(0) + 1e-9
        w = logreg_fit((Ftr - mu) / sd, y_tr, lam=2.0)  # λ doublé : 4 features à n=145
        Xte = np.column_stack([np.ones(te.sum()), (Fte - mu) / sd])
        p = 1.0 / (1.0 + np.exp(-(Xte @ w)))
        pred[te] = (p > 0.5).astype(int)
        conf[te] = np.abs(p - 0.5)
        sco[te] = p
    out["variants"]["C1_gxf_4espaces"] = report(
        "C1 GxF 4 espaces (λ=2)", pred, conf, sco, y, maj)

    # --- R1 : temporel — train frozen32+rct+boltzmann → test extension-128 ---
    mask_tr = camps != "extension-128"
    mask_te = camps == "extension-128"
    if mask_te.sum() > 10 and mask_tr.sum() > 10:
        en = eU
        thr = np.median(en[mask_tr])
        pred_r = (en[mask_te] < thr).astype(int)
        k = int((pred_r == y[mask_te]).sum())
        m = int(mask_te.sum())
        lo, hi = wilson(k, m)
        s_t = -en[mask_te]
        auc_r = auc(s_t[y[mask_te] == 1], s_t[y[mask_te] == 0])
        out["variants"]["R1_temporel"] = {
            "note": "train=campagnes gelées/RCT/boltzmann, test=extension-128 (postérieure)",
            "n_train": int(mask_tr.sum()), "n_test": m,
            "acc": k / m, "wilson95": [lo, hi], "auc": auc_r}
        print(f"R1 temporel (train n={mask_tr.sum()} → ext-128 n={m}) : "
              f"acc {k/m:.3f} [{lo:.3f},{hi:.3f}] AUC {auc_r:.3f}")

    (PILOT / "s10-scamper.json").write_text(json.dumps(out, indent=1))
    print(f"\nartefact : {PILOT / 's10-scamper.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
