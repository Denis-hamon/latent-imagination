#!/usr/bin/env python3
"""Story 10.3 — recalibration serving sur pool v10 + porte de régime.

Généralisation BIT-IDENTIQUE de flywheel_recalibrate.py (9.1) :
    score = d(nearest fail) − d(nearest pass), LOAO F1 ;
    thr = médiane pool figée ; conf = |score − thr| ;
    régime = top-10 % en conf, acc + Wilson.

PORTE PRÉ-DÉCLARÉE (avant de regarder v10) :
  - contrôle positif v6 (GOLD, géométrie v6 figée) : AUC 0.822 ± 0.01 et
    acc@100 % 0.779 ± 0.005 — la machinerie n'a pas dérivé ;
  - régime v10 : acc@10 % ≥ acc@10 % v9 − 0.01 (pas de régression).
Si la porte échoue : PAS DE PROMOTION, rapport divulgué, v9 reste servi.

HONNÊTETÉ DU QUOTA FLYWHEEL (10.2) : le delta promu est mono-classe positive
(6 lignes, 0 négatif — toutes groundées par exécution réelle) : la gate
ext-only LOAO-AUC (≤ 0.65 ⇒ exclusion) y est DÉGÉNÉRÉE (AUC indéfini sur une
seule classe ; « indéfini ≠ conforme », pas de chiffre fabriqué). La
protection contre la dégradation de l'instrument est portée par la présente
porte (contrôle + régime), comme en 9.1 — les deux constats sont disclosés
dans le rapport.

Tourne sur numpy seul — node ou local.
Run: uv run python scripts/act2/promote_v10_gate.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
CALIB_DIR = ROOT / "governance" / "act2" / "arm-artifacts"
V9_CALIB = CALIB_DIR / "risk-scan-v9-calibration.json"
V10_CALIB = CALIB_DIR / "risk-scan-v10-calibration.json"
GATE_REPORT = PILOT / "mcp-flywheel" / "promotion-gate-v10.json"

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
    f1 = s11._loao_f1_features(cd, tasks, y)
    thr = float(np.median(f1))
    conf = np.abs(f1 - thr)
    n_cov = max(1, round(len(y) * coverage))
    order = np.argsort(-conf)
    sel = order[:n_cov]
    pred = (f1 > thr).astype(int)
    k = int((pred[sel] == y[sel]).sum())
    lo, hi = s11.wilson(k, n_cov)
    return {"thr_pool": thr, "tau": float(conf[order[n_cov - 1]]),
            "coverage": coverage, "n_cov": n_cov, "k_correct": k,
            "acc_regime": k / n_cov, "wilson95": [lo, hi],
            "acc_LOAO_full": float((pred == y).mean())}


def _coverage(rows: list[dict]) -> dict:
    fams = Counter(r["task"].split(".")[0] for r in rows)
    return {"familles": len(fams), "familles_lte3": sum(1 for c in fams.values() if c <= 3),
            "par_famille": dict(sorted(fams.items()))}


def main() -> int:
    if not V9_CALIB.is_file():
        print("ABSENT: calibration v9 — référence de la porte manquante.")
        return 2
    cal9 = json.loads(V9_CALIB.read_text())

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

    rows9, y9, t9, cd9, *_ = _pool("v9")
    reg9 = _serving_regime(cd9, y9, t9)
    print(f"rappel v9 servi : thr {cal9['thr_pool']:.6f} · tau {cal9['tau_10pct']:.6f} "
          f"· recalcul thr {reg9['thr_pool']:.6f} · acc@10 {reg9['acc_regime']:.4f}")

    try:
        rows10, y10, t10, cd10, *_ = _pool("v10")
    except FileNotFoundError:
        print("ABSENT: pool v10 — lancer promote_v10_embed.py d'abord.")
        return 2
    reg10 = _serving_regime(cd10, y10, t10)
    regime_ok = reg10["acc_regime"] >= reg9["acc_regime"] - 0.01
    gate_ok = ctrl_ok and regime_ok
    print(f"v10 : thr {reg10['thr_pool']:.6f} · tau {reg10['tau']:.6f} · "
          f"acc@10 {reg10['acc_regime']:.4f} [{reg10['wilson95'][0]:.4f}, "
          f"{reg10['wilson95'][1]:.4f}] (n={reg10['n_cov']}) · "
          f"acc LOAO plein {reg10['acc_LOAO_full']:.4f}")
    print(f"PORTE : contrôle v6 {'OK' if ctrl_ok else 'FAIL'} ∧ régime v10 "
          f"{'OK' if regime_ok else 'FAIL'} → {'PROMOUVABLE' if gate_ok else 'PAS DE PROMOTION'}")

    delta = rows10[len(rows9):]
    pos10 = int(y10.sum())
    cal10 = {
        "pool": "latent-pool-v10.json",
        "n": len(rows10),
        "positifs": pos10,
        "majority": float(max(y10.mean(), 1 - y10.mean())),
        "recipe": "score = d(nearest fail) - d(nearest pass), LOAO F1; "
                  "thr = médiane pool figée; conf=|score-thr| "
                  "(identique v8/v9 — recette servie inchangée)",
        "thr_pool": reg10["thr_pool"],
        "tau_10pct": reg10["tau"],
        "predict_regime": {
            "coverage": reg10["coverage"],
            "n": reg10["n_cov"],
            "acc_measured_serving_recipe": reg10["acc_regime"],
            "wilson95": reg10["wilson95"],
            "acc_measured_LOAO": round(reg10["acc_LOAO_full"], 3),
            "note": "pred si conf>=tau_10pct, sinon abstain",
        },
        "goal_free_rows": sum(1 for r in rows10 if r.get("goal_free")),
        "gate": {
            "positive_control_v6": {"expected": [0.822, 0.779],
                                    "got": [round(ctrl["auc"], 3), round(ctrl["acc100"], 3)],
                                    "ok": bool(ctrl_ok)},
            "regime_no_regression": {"v9_acc10": reg9["acc_regime"],
                                     "v10_acc10": reg10["acc_regime"],
                                     "tolerance": 0.01, "ok": bool(regime_ok)},
            "promotable": bool(gate_ok),
        },
    }
    report = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "story": "10.3-pool-v10-promotion-family-evaluation",
        "v9_seal_ref": {"rows": len(rows9), "positives": int(y9.sum())},
        "v10": {"rows": len(rows10), "positives": pos10,
                "flywheel_delta_added": len(delta),
                "delta_tasks": [r["task"] for r in delta],
                "delta_campaigns": dict(Counter(r.get("campaign") for r in delta)),
                "delta_y": dict(Counter(r["y"] for r in delta))},
        "quota_flywheel_honesty": {
            "ext_only_loao_auc": None,
            "raison": "delta mono-classe positive (6 y=1, 0 négatif, tous groundés "
                      "par exécution réelle) — AUC LOAO ext-only INDÉFINI sur une "
                      "classe unique ; indéfini ≠ conforme, aucun chiffre fabriqué. "
                      "La protection de l'instrument est portée par la porte "
                      "contrôle+régime (précédent 9.1), mesurée ci-dessous.",
            "strata": "mcp-flywheel-1 distinct de genfam-q1 (quota genfam EXCLU : "
                      "poison 0.4918 < 0.65, bilan 2026-08-16)"},
        "coverage": {"v9": _coverage(rows9), "v10": _coverage(rows10)},
        "regime": {"v9_acc10": reg9["acc_regime"], "v9_tau": reg9["tau"],
                   "v10_acc10": reg10["acc_regime"], "v10_tau": reg10["tau"],
                   "v10_thr": reg10["thr_pool"], "v10_wilson95": reg10["wilson95"]},
        "gate": cal10["gate"],
        "decision": "PROMOTE (swap via LI_POOL_JSON/LI_POOL_NPZ/LI_RISK_CALIB)"
        if gate_ok else "HOLD — v9 reste servi, diagnostic requis",
    }
    GATE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    GATE_REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    if gate_ok:
        CALIB_DIR.mkdir(parents=True, exist_ok=True)
        V10_CALIB.write_text(json.dumps(cal10, indent=1, ensure_ascii=False) + "\n")
        print(f"ÉCRIT : {V10_CALIB.name} + {GATE_REPORT.name}")
    else:
        print(f"ÉCRIT : {GATE_REPORT.name} seulement (calibration v10 retenue — porte fermée)")
    return 0 if gate_ok else 3


if __name__ == "__main__":
    sys.exit(main())
