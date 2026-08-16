#!/usr/bin/env python3
"""Bras migration jina (prereg 3b345cdd) — gate de promotion pool v11.

Recette identique flywheel_recalibrate/promote_v10_gate, transposée à la
migration d'ESPACE (aucune ligne changée : v11 = v10 re-embeddé jina) :
  - ancre v6-GOLD re-mesurée dans l'espace jina (loao_energy, même recette ;
    valeur attendue 0.8315/0.7793 ± 0.01, enregistrée au bras — l'ancienne
    ancre unixcoder 0.822/0.779 ne s'applique plus, espaces incompatibles) ;
  - régime servi : thr = médiane f1 pool, conf = |f1−thr|, tau_10pct,
    acc@10% descriptive sur lignes groundées ;
  - conforme réalisé <= garanti (risk-scan-v11-conformal.json) ;
  - reproductibilité pooled4 jina 0.7428 ± 0.01 (dérive d'implémentation
    interdite entre l'embedding node et la mesure locale).
Sortie : risk-scan-v11-calibration.json + promotion-gate-v11.json
Run: uv run python scripts/act2/promote_v11_gate.py
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
ART = ROOT / "governance" / "act2" / "arm-artifacts"
_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)


def _pool(name: str):
    rows = json.loads((PILOT / f"latent-pool-{name}.json").read_text())
    d = np.load(PILOT / f"latent-pool-{name}.npz")
    y = np.array([int(r["y"]) for r in rows])
    t = np.array([str(r.get("task", i)) for i, r in enumerate(rows)])
    return rows, y, t, d


def main() -> int:
    rows11, y11, t11, d11 = _pool("v11")
    cd = s11.norm(s11.norm(d11["E_state"]) + s11.norm(d11["E_diff"]))
    f1 = s11._loao_f1_features(cd, t11, y11)
    thr = float(np.median(f1))
    conf = np.abs(f1 - thr)
    n_cov = max(1, round(len(y11) * 0.10))
    order = np.argsort(-conf)
    sel = order[:n_cov]
    acc10 = float((np.sign(f1 - thr)[sel] == (2 * y11[sel] - 1)).all()) if False else float(
        (((f1 > thr).astype(int))[sel] == y11[sel]).mean())
    regime = {"thr_pool": round(thr, 6), "tau_10pct": round(float(conf[order[n_cov - 1]]), 6),
              "coverage": 0.10, "acc_regime_10pct": round(acc10, 4)}

    # ancre v6-GOLD espace jina (recette contrôle identique)
    rows6, y6, t6, _ = _pool("v6")
    key = lambda r: (r.get("task"), (r.get("state") or "")[:200], (r.get("diff") or "")[:200])
    idx = {key(r): i for i, r in enumerate(rows11)}
    m = np.array([idx[key(r)] for r in rows6])
    assert len(m) == len(rows6), f"v6 non entièrement retrouvé dans v11 : {len(m)}/{len(rows6)}"
    Es, Ed, Eg = (s11.norm(d11[k][m]) for k in ("E_state", "E_diff", "E_goal"))
    p6, c6, s6 = s11.loao_energy(s11.norm(Es + Ed), s11.norm(Es + Eg), y6, t6)
    ctrl = s11.report("ANCRE v6 GOLD espace jina", p6, c6, s6, y6,
                      max(float(y6.mean()), 1 - float(y6.mean())))
    ctrl_ok = abs(ctrl["auc"] - 0.8315) < 0.01 and abs(ctrl["acc100"] - 0.7793) < 0.005

    # conforme réalisé <= garanti
    conf_file = ART / "risk-scan-v11-conformal.json"
    confd = json.loads(conf_file.read_text())
    g10 = confd["global_conformal"]["alpha_0.10"]["realized_err_rate"]
    conf_ok = g10 <= 0.10 + 1e-9

    # reproductibilité pooled4 (artefact du re-test)
    rep = json.loads((ART / "embedder-retest-jina-pooled4-2026-08-17.json").read_text())
    reprod_ok = abs(rep["jina"]["auc"] - 0.7428) <= 0.01

    calib = {"pool": "v11", "encoder": "jina-v2-base-code", "n": len(y11),
             "positifs": int((y11 == 1).sum()),
             "recipe": "LOAO-F1 goal-free sur E_state+E_diff (identique v9/v10)",
             **regime, "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    (ART / "risk-scan-v11-calibration.json").write_text(json.dumps(calib, indent=1, ensure_ascii=False) + "\n")
    gate = {"gate": "migration-jina-v11", "prereg": "3b345cdd",
            "ancre_v6_gold_jina": {"auc": round(float(ctrl["auc"]), 4),
                                   "acc100": round(float(ctrl["acc100"]), 4), "ok": bool(ctrl_ok)},
            "conforme_realise_alpha_0_10": {"erreur": g10, "garantie": 0.10, "ok": bool(conf_ok)},
            "reproductibilite_pooled4": {"auc": rep["jina"]["auc"], "attendu": 0.7428, "ok": bool(reprod_ok)},
            "regime_10pct": regime,
            "verdict": "PROMOUVABLE" if (ctrl_ok and conf_ok and reprod_ok) else "NON PROMOUVABLE",
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "disclosure": "espaces unixcoder/jina incompatibles : aucun seuil v10 réutilisé ; l'ancre 0.822/0.779 unixcoder est remplacée par 0.8315/0.7793 jina"}
    (ART / "promotion-gate-v11.json").write_text(json.dumps(gate, indent=1, ensure_ascii=False) + "\n")
    print(f"ancre v6 jina : AUC {ctrl['auc']:.4f} acc100 {ctrl['acc100']:.4f} → {'OK' if ctrl_ok else 'DÉRIVE'}")
    print(f"conforme α=0.10 : err {g10:.3f} ≤ 0.10 → {'OK' if conf_ok else 'ÉCHEC'}")
    print(f"reprod pooled4 : {rep['jina']['auc']} → {'OK' if reprod_ok else 'ÉCHEC'}")
    print(f"régime 10 % : thr {regime['thr_pool']} · tau {regime['tau_10pct']} · acc@10 {regime['acc_regime_10pct']}")
    print(f"VERDICT : {gate['verdict']}")
    return 0 if gate["verdict"] == "PROMOUVABLE" else 2


if __name__ == "__main__":
    sys.exit(main())
