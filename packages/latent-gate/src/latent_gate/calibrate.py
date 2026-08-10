"""Calibrage offline du modèle de production → public/artifacts/model.json

Ce qui est FIGÉ ici, hashé, et jamais refitté à chaud :
  - poids GxF (logreg λ=1) fittés sur TOUT le pool de prod (fit-final légitime :
    la procédure a été validée out-of-fold par S3/S7 ; 3 paramètres seulement)
  - features mu/sd (constantes du pipeline)
  - quantiles d'abstention q50/q75 = MESURÉS OUT-OF-FOLD (LOAO strict, un fold
    par tâche) — c'est la courbe publiée, pas un réglage à la main.

Le hash du pool est embarqué : toute promotion du pool (batch report_outcome)
invalide le hash → le service refuse de démarrer tant que model.json n'est pas
régénéré. C'est le verrou reproductibilité du produit.

Run : python -m latent_gate.calibrate --pool-dir <dir contenant latent-pool-v6.*>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from .scoring import norm_rows

OUT_DEFAULT = Path(__file__).resolve().parents[2] / "public" / "artifacts" / "model.json"

COVERAGES = (1.0, 0.75, 0.5, 0.4, 0.3, 0.25, 0.2, 0.1)


def logreg_fit(X: np.ndarray, y: np.ndarray, lam: float = 1.0,
               iters: int = 200) -> np.ndarray:
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


def wilson(k: int, n: int) -> tuple[float, float]:
    z = 1.96
    p = k / max(1, n)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = (z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return max(0.0, c - h), min(1.0, c + h)


def build_spec(pool_json: Path) -> tuple[dict, dict]:
    rows = json.loads(pool_json.read_text())
    d = np.load(str(pool_json).replace(".json", ".npz"))
    E_s = norm_rows(d["E_state"])
    E_d = norm_rows(d["E_diff"])
    E_g = norm_rows(d["E_goal"])
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    n = len(rows)

    cd = norm_rows(E_s + E_d)
    cg = norm_rows(E_s + E_g)
    energy = 1.0 - (cd * cg).sum(-1)

    # --- features GxF pour chaque point, attracteurs calculés LOAO par tâche ---
    f1_oof = np.zeros(n)
    for held in sorted(set(tasks)):
        te, tr = tasks == held, tasks != held
        cd_tr, y_tr = cd[tr], y[tr]
        sims = cd[te] @ cd_tr.T
        f1_oof[te] = ((1 - sims[:, y_tr == 0]).min(1)
                      - (1 - sims[:, y_tr == 1]).min(1))

    # --- 1) poids PROD : fit all-pool (constantes du modèle) ---
    F = np.column_stack([-energy, f1_oof])
    mu, sd = F.mean(0), F.std(0) + 1e-9
    w_full = logreg_fit((F - mu) / sd, y)

    # --- 2) quantiles d'abstention : LOAO strict (modèle refitté par fold) ---
    p_oof = np.zeros(n)
    for held in sorted(set(tasks)):
        te, tr = tasks == held, tasks != held
        e_tr = energy[tr]
        cd_tr, y_tr = cd[tr], y[tr]
        sims = cd[te] @ cd_tr.T
        f1_te = ((1 - sims[:, y_tr == 0]).min(1)
                 - (1 - sims[:, y_tr == 1]).min(1))
        f1_tr = ((1 - cd_tr @ cd_tr[y_tr == 0].T).min(1)
                 - (1 - cd_tr @ cd_tr[y_tr == 1].T).min(1))
        Ftr = np.column_stack([-e_tr, f1_tr])
        Fte = np.column_stack([-energy[te], f1_te])
        m, s = Ftr.mean(0), Ftr.std(0) + 1e-9
        w = logreg_fit((Ftr - m) / s, y_tr)
        Xte = np.column_stack([np.ones(te.sum()), (Fte - m) / s])
        p_oof[te] = 1.0 / (1.0 + np.exp(-(Xte @ w)))

    conf_oof = np.abs(p_oof - 0.5)
    q50, q75 = float(np.quantile(conf_oof, 0.5)), float(np.quantile(conf_oof, 0.75))

    # courbe publiée (témoin LOAO complet, pour le README et l'eval pack)
    pred_oof = (p_oof > 0.5).astype(int)
    curve = []
    order = np.argsort(-conf_oof)
    maj = max(y.mean(), 1 - y.mean())
    for cov in COVERAGES:
        m2 = max(1, int(round(n * cov)))
        sel = order[:m2]
        k = int((pred_oof[sel] == y[sel]).sum())
        lo, hi = wilson(k, m2)
        curve.append({"coverage": cov, "n": m2, "acc": k / m2,
                      "wilson95": [lo, hi]})

    pool_bytes = pool_json.read_bytes() + d["E_state"].tobytes()
    spec = {
        "recipe": "gxf-logreg-l1",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n": n, "positives": int(y.sum()), "tasks": len(set(tasks)),
        "majority": float(maj),
        "gxf": {"w": w_full[1:].tolist(), "b": float(w_full[0]),
                "feat_mu": mu.tolist(), "feat_sd": sd.tolist()},
        "abstention": {"q50": q50, "q75": q75,
                       "note": "quantiles de |p-0.5| mesurés LOAO (out-of-fold)"},
        "oof_witness_curve": curve,
        "pool_sha256": hashlib.sha256(pool_bytes).hexdigest(),
        "pool_source": pool_json.name,
    }
    return spec, {"p_oof": p_oof.tolist(), "y": y.tolist(),
                  "conf_oof": conf_oof.tolist()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool-dir", required=True)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    pool_json = Path(args.pool_dir) / "latent-pool-v6.json"
    spec, witness = build_spec(pool_json)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=1))
    (out.parent / "model-witness.json").write_text(json.dumps(witness))
    print(f"model.json écrit : {out}")
    print(f"  sha256 {hashlib.sha256(out.read_bytes()).hexdigest()}")
    print(f"  n={spec['n']} pos={spec['positives']} "
          f"q50={spec['abstention']['q50']:.4f} q75={spec['abstention']['q75']:.4f}")
    for c in spec["oof_witness_curve"]:
        print(f"  cov {c['coverage']:4.0%} n={c['n']:3d} acc {c['acc']:.3f} "
              f"[{c['wilson95'][0]:.3f},{c['wilson95'][1]:.3f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
