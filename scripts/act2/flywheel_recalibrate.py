#!/usr/bin/env python3
"""Story 9.1 — recalibration serving sur pool v9 + porte de régime.

Recette EXACTE du fichier servi v8 (risk-scan-v8-calibration.json) :
    score = d(nearest fail) − d(nearest pass), LOAO F1 ;
    thr = médiane pool figée ; conf = |score − thr| ;
    régime = top-10 % en conf, acc + Wilson.
Implémentée via s11._loao_f1_features (le calcul LOAO exact par chunks).

PORTE PRÉ-DÉCLARÉE (avant de regarder v9) :
  - contrôle positif v6 (GOLD, sur la géométrie v6 figée) : AUC 0.822 ± 0.01
    et acc@100 % 0.779 ± 0.005 — la machinerie n'a pas dérivé ;
  - régime v9 : acc@10 % ≥ acc@10 % v8 − 0.01 (pas de régression du régime).
Si la porte échoue : PAS DE PROMOTION, rapport divulgué, v8 reste servi.

Tourne sur numpy seul (géométrie) — node ou local.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
CALIB_DIR = ROOT / "governance" / "act2" / "arm-artifacts"
V8_CALIB = CALIB_DIR / "risk-scan-v8-calibration.json"
V9_CALIB = CALIB_DIR / "risk-scan-v9-calibration.json"
GATE_REPORT = PILOT / "mcp-flywheel" / "promotion-gate-v9.json"

_spec = importlib.util.spec_from_file_location(
    "s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s11)


def _pool(name: str):
    rows = json.loads((PILOT / f"latent-pool-{name}.json").read_text())
    d = np.load(PILOT / f"latent-pool-{name}.npz")
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    Es, Ed, Eg = (s11.norm(d[k]) for k in ("E_state", "E_diff", "E_goal"))
    cd = s11.norm(Es + Ed)
    return rows, y, tasks, cd, Es, Ed, Eg


def _serving_regime(cd, y, tasks, coverage: float = 0.10) -> dict:
    """La recette servie : LOAO F1, thr médiane, régime top-coverage."""
    f1 = s11._loao_f1_features(cd, tasks, y)
    thr = float(np.median(f1))
    conf = np.abs(f1 - thr)
    n_cov = max(1, round(len(y) * coverage))
    order = np.argsort(-conf)
    sel = order[:n_cov]
    pred = (f1 > thr).astype(int)
    k = int((pred[sel] == y[sel]).sum())
    lo, hi = s11.wilson(k, n_cov)
    acc_all = float((pred == y).mean())
    return {"thr_pool": thr, "tau": float(conf[order[n_cov - 1]]),
            "coverage": coverage, "n_cov": n_cov, "k_correct": k,
            "acc_regime": k / n_cov, "wilson95": [lo, hi],
            "acc_LOAO_full": acc_all}


def main() -> int:
    if not V8_CALIB.is_file():
        print("ABSENT: calibration v8 — référence de la porte manquante.")
        return 2
    cal8 = json.loads(V8_CALIB.read_text())

    # --- contrôle positif v6 (machinerie intacte, vérité historique figée) ---
    _, y6, t6, _, Es6, Ed6, Eg6 = _pool("v6")
    pred6, conf6, sco6 = s11.loao_energy(s11.norm(Es6 + Ed6),
                                         s11.norm(Es6 + Eg6), y6, t6)
    ctrl = s11.report("CTRL v6 GOLD", pred6, conf6, sco6, y6,
                      max(y6.mean(), 1 - y6.mean()))
    ctrl_ok = (abs(ctrl["auc"] - 0.822) < 0.01
               and abs(ctrl["acc100"] - 0.779) < 0.005)
    print(f"contrôle v6 : AUC {ctrl['auc']:.3f} (exp 0.822) · "
          f"acc100 {ctrl['acc100']:.3f} (exp 0.779) → "
          f"{'OK' if ctrl_ok else 'DÉRIVE'}")

    # --- v8 : rappel du régime servi ---
    rows8, y8, t8, cd8, *_ = _pool("v8")
    reg8 = _serving_regime(cd8, y8, t8)
    print(f"rappel v8 servi : thr {cal8['thr_pool']:.6f} · tau {cal8['tau_10pct']:.6f} "
          f"· recalcul thr {reg8['thr_pool']:.6f} · acc@10 {reg8['acc_regime']:.4f}")

    # --- v9 : recalibration + porte ---
    try:
        rows9, y9, t9, cd9, *_ = _pool("v9")
    except FileNotFoundError:
        print("ABSENT: pool v9 — lancer flywheel_embed.py d'abord.")
        return 2
    reg9 = _serving_regime(cd9, y9, t9)
    regime_ok = reg9["acc_regime"] >= reg8["acc_regime"] - 0.01
    gate_ok = ctrl_ok and regime_ok
    print(f"v9 : thr {reg9['thr_pool']:.6f} · tau {reg9['tau']:.6f} · "
          f"acc@10 {reg9['acc_regime']:.4f} [{reg9['wilson95'][0]:.4f}, "
          f"{reg9['wilson95'][1]:.4f}] (n={reg9['n_cov']}) · "
          f"acc LOAO plein {reg9['acc_LOAO_full']:.4f}")
    print(f"PORTE : contrôle v6 {'OK' if ctrl_ok else 'FAIL'} ∧ régime v9 "
          f"{'OK' if regime_ok else 'FAIL'} → {'PROMOUVABLE' if gate_ok else 'PAS DE PROMOTION'}")

    # --- artefacts : calibration v9 + rapport de porte ---
    pos9 = int(y9.sum())
    cal9 = {
        "pool": "latent-pool-v9.json",
        "n": len(rows9),
        "positifs": pos9,
        "majority": float(max(y9.mean(), 1 - y9.mean())),
        "recipe": "score = d(nearest fail) - d(nearest pass), LOAO F1; "
                  "thr = médiane pool figée; conf=|score-thr| "
                  "(identique v8 — recette servie inchangée)",
        "thr_pool": reg9["thr_pool"],
        "tau_10pct": reg9["tau"],
        "predict_regime": {
            "coverage": reg9["coverage"],
            "n": reg9["n_cov"],
            "acc_measured_serving_recipe": reg9["acc_regime"],
            "wilson95": reg9["wilson95"],
            "acc_measured_LOAO": round(reg9["acc_LOAO_full"], 3),
            "note": "pred si conf>=tau_10pct, sinon abstain",
        },
        "goal_free_rows": sum(1 for r in rows9 if r.get("goal_free")),
        "gate": {
            "positive_control_v6": {"expected": [0.822, 0.779],
                                    "got": [round(ctrl["auc"], 3), round(ctrl["acc100"], 3)],
                                    "ok": bool(ctrl_ok)},
            "regime_no_regression": {"v8_acc10": reg8["acc_regime"],
                                     "v9_acc10": reg9["acc_regime"],
                                     "tolerance": 0.01, "ok": bool(regime_ok)},
            "promotable": bool(gate_ok),
        },
    }
    report = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "story": "9.1-first-promotion-ceremony-pool-v9",
        "v8_seal_ref": {"rows": len(rows8), "positives": int(y8.sum())},
        "v9": {"rows": len(rows9), "positives": pos9,
               "flywheel_rows_added": len(rows9) - len(rows8)},
        "regime": {"v8_acc10": reg8["acc_regime"], "v8_tau": reg8["tau"],
                   "v9_acc10": reg9["acc_regime"], "v9_tau": reg9["tau"],
                   "v9_thr": reg9["thr_pool"], "v9_wilson95": reg9["wilson95"]},
        "gate": cal9["gate"],
        "decision": "PROMOTE (swap via LI_POOL_JSON/LI_POOL_NPZ/LI_RISK_CALIB)"
        if gate_ok else "HOLD — v8 reste servi, diagnostic requis",
    }
    CALIB_DIR.mkdir(parents=True, exist_ok=True)
    GATE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    (GATE_REPORT).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    # La calibration v9 n'est ÉCRITE que si la porte passe (sinon rien ne sert v9)
    if gate_ok:
        V9_CALIB.write_text(json.dumps(cal9, indent=1, ensure_ascii=False) + "\n")
        print(f"ÉCRIT : {V9_CALIB} + {GATE_REPORT.name}")
    else:
        print(f"ÉCRIT : {GATE_REPORT.name} seulement (calibration v9 retenue — porte fermée)")
    return 0 if gate_ok else 3


if __name__ == "__main__":
    sys.exit(main())
