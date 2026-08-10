#!/usr/bin/env python3
"""S3 — améliorer l'instrument sans toucher aux données : confiance + combinaison.

Deux questions posées à 0 call galere, sur le pool figé (latent-pool.json/npz) :

  Q1 (confiance) : la marge brute |score − seuil| (S1) est-elle le meilleur
     estimateur de "quand l'instrument sait" ? Alternatives testées, toutes LOAO :
       - platt   : régression logistique 1-feature fit train → conf |p − 0.5|
       - boot    : consensus bootstrap (B=200 refits logreg) — capture la
                   sensibilité au train, pas juste la distance au seuil
       - density : proximité aux k=5 plus proches voisins train (espace
                   state+diff normalisé) — confiance épistémique du support
  Q2 (combinaison) : GOLD (goal-bound) et F1 (répulsion d'échecs) sont quasi
     orthogonaux (Spearman +0.187, rang-moyen naïf AUC 0.838). Une combinaison
     APRISE (logreg 2 features, fit train du fold uniquement) dépasse-t-elle
     le rang-moyen sur la métrique produit : la couverture à acc ≥ 0.95 ?

Garde-fous : LOAO-strict (tout fit = train du fold ; attracteurs F1 train-only ;
la couverture est décidée globalement APRÈS assignation des confiances hors-pli,
protocole identique à S1). Métrique de succès déclarée AVANT calcul : couverture
maximale atteignant acc ≥ 0.95 avec borne basse Wilson95 > majorité (0.611).

Note de session (mesurée avant ce run) : la logreg 2D à λ=1e-3 SÉPARE COMPLÈTEMENT
sur les folds train (poids médians biais −7.2, F1 +25.1, GOLD ignoré) → instable.
On fixe λ=1.0 pour lui donner une chance honnête, et on ajoute le combinateur
NaÏF (z-somme, mu/sd train-only, 0 paramètre appris) qui vaut AUC 0.863 en global
vs 0.837 rang-moyen (repro G1) et 0.817 GOLD seul.

Contrôle positif : le bras GOLD+margin DOIT reproduire S1 (1.000 @ 25 %).

Sortie : data/landing/act2-pilot/s3-confidence.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
RNG = np.random.default_rng(20260810)
B_BOOT = 200
COVERAGES = (1.0, 0.9, 0.75, 0.6, 0.5, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15, 0.10)
TARGET_ACC = 0.95


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
    s, f = np.asarray(succ), np.asarray(fail)
    diff = s[:, None] - f[None, :]
    return float((np.sum(diff > 0) + 0.5 * np.sum(diff == 0)) / diff.size)


def logreg_fit(X, y, lam=1.0, iters=200):
    """Newton-Raphson, features standardisées en entrée. Retourne w (d+1,)."""
    Xb = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(Xb.shape[1])
    for _ in range(iters):
        z = Xb @ w
        p = 1.0 / (1.0 + np.exp(-z))
        g = Xb.T @ (p - y) + lam * w
        W = p * (1 - p) + 1e-9
        H = (Xb * W[:, None]).T @ Xb + lam * np.eye(Xb.shape[1])
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def logreg_predict(X, w):
    Xb = np.column_stack([np.ones(len(X)), X])
    return 1.0 / (1.0 + np.exp(-(Xb @ w)))


def standardize(Xtr, Xte):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    return (Xtr - mu) / sd, (Xte - mu) / sd


def main() -> int:
    rows = json.loads((PILOT / "latent-pool.json").read_text())
    d = np.load(PILOT / "latent-pool.npz")
    E_s, E_d, E_g = norm(d["E_state"]), norm(d["E_diff"]), norm(d["E_goal"])
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    n = len(rows)
    maj = max(y.mean(), 1 - y.mean())
    cd, cg = norm(E_s + E_d), norm(E_s + E_g)
    energy = 1.0 - (cd * cg).sum(-1)  # bas = succès

    uniq = sorted(set(tasks))
    # chaque méthode : (score_orienté[haut=succès], confiance, pred) hors-pli
    methods = {k: np.zeros((n, 3)) for k in
               ("GOLD+margin", "GOLD+platt", "GOLD+boot", "GOLD+density",
                "GxF+zsum", "GxF+zsum+minmarg", "GxF+platt", "GxF+boot")}

    for held in uniq:
        te_mask = tasks == held
        tr_mask = ~te_mask
        ti = np.where(te_mask)[0]
        e_tr, e_te = energy[tr_mask], energy[ti]
        y_tr = y[tr_mask]

        # --- axe GOLD ---
        thr = np.median(e_tr)
        methods["GOLD+margin"][ti, 0] = -e_te
        methods["GOLD+margin"][ti, 1] = np.abs(e_te - thr)
        methods["GOLD+margin"][ti, 2] = (e_te < thr).astype(int)  # prédiction S1 exacte

        Xtr, Xte = standardize(e_tr.reshape(-1, 1), e_te.reshape(-1, 1))
        w = logreg_fit(Xtr, y_tr)
        p_g = logreg_predict(Xte, w)
        methods["GOLD+platt"][ti, 0] = p_g
        methods["GOLD+platt"][ti, 1] = np.abs(p_g - 0.5)
        methods["GOLD+platt"][ti, 2] = (p_g > 0.5).astype(int)

        # --- axe F1 (attracteurs train-only, protocole S1 identique) ---
        cd_tr = cd[tr_mask]
        sims = cd[ti] @ cd_tr.T
        d_fail = 1 - sims[:, y_tr == 0]
        d_pass = 1 - sims[:, y_tr == 1]
        f1_te = d_fail.min(1) - d_pass.min(1)  # haut = proche succès
        f1_tr = ((1 - cd_tr @ cd_tr[y_tr == 0].T).min(1)
                 - (1 - cd_tr @ cd_tr[y_tr == 1].T).min(1))

        # --- bootstrap consensus (GOLD seul) ---
        probs_b = np.zeros((B_BOOT, len(ti)))
        ntr = len(e_tr)
        for b in range(B_BOOT):
            idx = RNG.integers(0, ntr, ntr)
            if len(set(y_tr[idx])) < 2:  # tirage dégénéré
                probs_b[b] = np.nan
                continue
            wb = logreg_fit(Xtr[idx], y_tr[idx])
            probs_b[b] = logreg_predict(Xte, wb)
        p_bar = np.nanmean(probs_b, axis=0)
        consensus = np.maximum(p_bar, 1 - p_bar)  # ∈ [0.5, 1]
        methods["GOLD+boot"][ti, 0] = p_bar
        methods["GOLD+boot"][ti, 1] = consensus
        methods["GOLD+boot"][ti, 2] = (p_bar > 0.5).astype(int)

        # --- densité k-NN locale (espace cd, train seul) ---
        d_nn = np.sort(1 - sims, axis=1)[:, :5].mean(1)  # dist cos aux 5 PPv
        methods["GOLD+density"][ti, 0] = -e_te
        methods["GOLD+density"][ti, 1] = -d_nn
        methods["GOLD+density"][ti, 2] = (e_te < thr).astype(int)  # même pred que margin

        # --- combinaison NAÏVE z-somme (mu/sd train-only, 0 param appris) ---
        g_tr = -e_tr  # haut = succès
        mu_g, sd_g = g_tr.mean(), g_tr.std() + 1e-9
        mu_f, sd_f = f1_tr.mean(), f1_tr.std() + 1e-9
        zsum_tr = (g_tr - mu_g) / sd_g + (f1_tr - mu_f) / sd_f
        z_g = (-e_te - mu_g) / sd_g
        z_f = (f1_te - mu_f) / sd_f
        zsum_te = z_g + z_f
        thr_z = np.median(zsum_tr)
        methods["GxF+zsum"][ti, 0] = zsum_te
        methods["GxF+zsum"][ti, 1] = np.abs(zsum_te - thr_z)
        methods["GxF+zsum"][ti, 2] = (zsum_te > thr_z).astype(int)
        # variante conjonctive : confiant si les DEUX axes sont loin de leur seuil
        thr_g = np.median(g_tr)
        thr_f = np.median(f1_tr)
        marg_g = np.abs((-e_te - thr_g)) / sd_g
        marg_f = np.abs(f1_te - thr_f) / sd_f
        methods["GxF+zsum+minmarg"][ti, 0] = zsum_te
        methods["GxF+zsum+minmarg"][ti, 1] = np.minimum(marg_g, marg_f)
        methods["GxF+zsum+minmarg"][ti, 2] = (zsum_te > thr_z).astype(int)

        # --- combinaison apprise GOLD × F1 (logreg 2 features, fit train) ---
        Ftr = np.column_stack([-e_tr, f1_tr])
        Fte = np.column_stack([-e_te, f1_te])
        Ftr_s, Fte_s = standardize(Ftr, Fte)
        wc = logreg_fit(Ftr_s, y_tr)
        p_c = logreg_predict(Fte_s, wc)
        methods["GxF+platt"][ti, 0] = p_c
        methods["GxF+platt"][ti, 1] = np.abs(p_c - 0.5)
        methods["GxF+platt"][ti, 2] = (p_c > 0.5).astype(int)

        probs_c = np.zeros((B_BOOT, len(ti)))
        for b in range(B_BOOT):
            idx = RNG.integers(0, ntr, ntr)
            if len(set(y_tr[idx])) < 2:
                probs_c[b] = np.nan
                continue
            Fb, _ = standardize(Ftr[idx], Ftr[idx])  # standardisation intra-tirage
            wcb = logreg_fit(Fb, y_tr[idx])
            Fte_b = (Fte - Ftr[idx].mean(0)) / (Ftr[idx].std(0) + 1e-9)
            probs_c[b] = logreg_predict(Fte_b, wcb)
        p_cbar = np.nanmean(probs_c, axis=0)
        methods["GxF+boot"][ti, 0] = p_cbar
        methods["GxF+boot"][ti, 1] = np.maximum(p_cbar, 1 - p_cbar)
        methods["GxF+boot"][ti, 2] = (p_cbar > 0.5).astype(int)

    # --- courbes couverture/acc, couverture décidée globalement après hors-pli ---
    out = {"n": n, "majority": float(maj), "B_boot": B_BOOT,
           "target_acc": TARGET_ACC, "methods": {}}
    for name, R in methods.items():
        score, conf, pred = R[:, 0], R[:, 1], R[:, 2].astype(int)
        curve = []
        order = np.argsort(-conf)
        for cov in COVERAGES:
            m = max(1, int(round(n * cov)))
            sel = order[:m]
            k = int((pred[sel] == y[sel]).sum())
            lo, hi = wilson(k, m)
            curve.append({"coverage": cov, "n": m, "acc": k / m,
                          "wilson95": [lo, hi]})
        # couverture max à acc >= cible avec borne basse > majorité
        best = 0.0
        for c in curve:
            if c["acc"] >= TARGET_ACC and c["wilson95"][0] > maj:
                best = max(best, c["coverage"])
        out["methods"][name] = {
            "auc_full": auc(score[y == 1].tolist(), score[y == 0].tolist()),
            "acc_full": curve[0]["acc"],
            "max_cov_at_target": best,
            "curve": curve,
        }

    print(f"\n===== S3 — confiance & combinaison LOAO, n={n} (majorité {maj:.3f}) =====")
    hdr = f"{'méthode':<14} {'AUC':>6} {'acc100':>7} {'cov@≥.95*':>9}"
    print(hdr + "   (*borne basse Wilson > majorité)")
    for name, a in out["methods"].items():
        print(f"{name:<14} {a['auc_full']:6.3f} {a['acc_full']:7.3f} "
              f"{a['max_cov_at_target']:9.0%}")
    print("\n--- courbes complètes ---")
    for name, a in out["methods"].items():
        print(f"\n{name}")
        for c in a["curve"]:
            print(f"  cov {c['coverage']:5.0%} | n={c['n']:3d} | acc {c['acc']:.3f} "
                  f"[{c['wilson95'][0]:.3f},{c['wilson95'][1]:.3f}]")

    # contrôle positif : repro S1 -> avertissement explicite si dérive
    g = out["methods"]["GOLD+margin"]
    s1_25 = next(c for c in g["curve"] if abs(c["coverage"] - 0.25) < 1e-9)
    ok = abs(s1_25["acc"] - 1.0) < 1e-9
    print(f"\ncontrôle positif (S1 GOLD+margin @25% == 1.000) : "
          f"{'OK' if ok else 'DÉRIVE ' + str(s1_25['acc'])}")
    out["positive_control_s1_25"] = {"expected": 1.0, "got": s1_25["acc"], "ok": ok}

    (PILOT / "s3-confidence.json").write_text(json.dumps(out, indent=1))
    print(f"artefact : {PILOT / 's3-confidence.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
