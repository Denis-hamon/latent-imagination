#!/usr/bin/env python3
"""Fenêtre v19 (5d0348089952e9b3) — calibration énergie goal sur pool v18.
S1 : AUC énergie LOAO (reproduction 0.7495 ±0.01) + Youden J >= 0.50.
Formule identique à energy_of serveur / loao_energy s11 : 1 - <cd, cg>.
Node GPU (cache embeddings v18). Run: .venv/bin/python scripts/act2/v19_calibrate_goal.py
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"


def norm(A):
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def main() -> int:
    rows = json.loads((PILOT / "ts-gold-v18" / "v18-rows.json").read_text())
    d = np.load(PILOT / "ts-gold-v18" / "v18-rows.emb.npz")
    Es, Ed, Eg = d["Es"], d["Ed"], d["Eg"]
    y = np.array([r["y"] for r in rows])
    cd, cg = norm(norm(Es) + norm(Ed)), norm(norm(Es) + norm(Eg))
    energy = 1.0 - (cd * cg).sum(-1)  # formule exacte de energy_of/loao_energy
    pos, neg = energy[y == 1], energy[y == 0]
    dd = neg[:, None] - pos[None, :]  # y=1 doit avoir l'énergie plus basse
    auc = float((np.sum(dd > 0) + 0.5 * np.sum(dd == 0)) / dd.size)
    # Youden sur le seuil énergie : pred pass = energy < thr
    best_j, best_thr = -1.0, 0.5
    for thr in np.unique(np.round(energy, 6)):
        pred = (energy < thr).astype(int)
        tp = ((pred == 1) & (y == 1)).sum(); fp = ((pred == 1) & (y == 0)).sum()
        fn = ((pred == 0) & (y == 1)).sum(); tn = ((pred == 0) & (y == 0)).sum()
        j = tp / max(1, tp + fn) - fp / max(1, fp + tn)
        if j > best_j:
            best_j, best_thr = float(j), float(thr)
    pred_all = (energy < best_thr).astype(int)
    acc_all = float((pred_all == y).mean())
    conf = np.abs(energy - best_thr)
    n_cov = max(1, round(len(y) * 0.10))
    sel = np.argsort(-conf)[:n_cov]
    cal = {"pool": "latent-pool-v18", "encoder": "jina-v2-base-code",
           "axis": "goal (1 - <E_state+E_diff, E_state+E_goal>)",
           "energy_threshold_youden": round(best_thr, 6), "youden_J": round(best_j, 4),
           "n": len(rows), "auc_energy_loao_note": "énergie row-wise, LOAO pred/conf "
           "dans loao_energy ; AUC ici = énergie brute (recette v18)",
           "auc_energy": round(auc, 4),
           "source": "window-v19 5d0348089952e9b3",
           "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    out = {"S1": {"auc_energy": round(auc, 4), "attendu_v18": 0.7495,
                  "ok_repro": abs(auc - 0.7495) <= 0.011, "youden_J": round(best_j, 4),
                  "ok_J": best_j >= 0.50, "threshold": round(best_thr, 6)},
           "S2_descriptif": {"acc_pleine_population": round(acc_all, 4),
                             "acc_top10conf": round(float((pred_all[sel] == y[sel]).mean()), 4),
                             "coverage": 0.10},
           "calibration": cal}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    (PILOT / "goal-calibration-v19.json").write_text(json.dumps(cal, indent=1, ensure_ascii=False) + "\n")
    (PILOT / "v19-S1S2-mesure.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    ok = abs(auc - 0.7495) <= 0.011 and best_j >= 0.50
    print("S1 :", "OK" if ok else "ÉCHEC")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
