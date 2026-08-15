#!/usr/bin/env python3
"""Recalibrage quotidien du predictor MCP à partir des outcomes réels.

Règle : retrainer UNIQUEMENT sur les logs réels (call_id) — pas de boucle de belief
fantôme. Le nouveau SIGMOID (w,b) est écrit dans predictor-mcp-calibration.json
avec update_count incrémenté, 100 % déterministe, Wilson consigné.

Honnêteté : à n < 30, la nouvelle calibration est fusionnée avec l'ancienne
(25 % nouveau, 75 % prédécent), sinon la dérive statistique domine.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "data" / "landing" / "act2-pilot" / "mcp-log.jsonl"
POOL = ROOT / "data" / "landing" / "act2-pilot" / "latent-pool.json"
CAL = ROOT / "governance/act2/arm-artifacts/predictor-mcp-calibration.json"


def wilson(k, n):
    if n == 0: return (0.0, 1.0)
    z = 1.96; p = k / n; den = 1 + z*z/n
    c = (p + z*z/(2*n)) / den; h = (z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / den
    return max(0, c-h), min(1, c+h)


def fit_logistic_pairs(pairs, epochs=400, lr=0.4, l2=1e-3):
    w, b = 1.0, 0.0
    for _ in range(epochs):
        for e, y in pairs:
            z = w * e + b
            p = 1/(1+math.exp(-max(-30, min(30, z))))
            g = p - y
            w -= lr * (g * e + l2 * w)
            b -= lr * g
    return w, b


def main() -> int:
    outcomes: dict[str, bool] = {}
    for ln in LOG.read_text().splitlines():
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if r.get("type") == "outcome":
            outcomes[r["call_id"]] = bool(r["passed"])
    call_energy: dict[str, float] = {}
    for ln in LOG.read_text().splitlines():
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if r.get("type") == "assess":
            call_energy[r["call_id"]] = float(r["energy"])
    joints = [(call_energy[k], outcomes[k]) for k in outcomes if k in call_energy]
    if not joints:
        print("0 outcomes joints — rien à recalibrer")
        return 0
    n_pos = sum(y for _, y in joints)
    # apprend
    w_new, b_new = fit_logistic_pairs(joints)
    base = json.loads(CAL.read_text()) if CAL.is_file() else {"w": 8.0, "b": -0.55, "mu": 0.026, "update_count": 0}
    # mélange honnête : n < 30 → poids contraints
    frac = 1.0 if len(joints) >= 30 else len(joints) / 30 * 0.25
    w = base["w"] * (1 - frac) + w_new * frac
    b = base["b"] * (1 - frac) + b_new * frac

    # validation LOO quick sur l'historique des outcomes_MSG seulement (pas le pool)
    hits = 0
    for i, (e, y) in enumerate(joints):
        tr = [p for j, p in enumerate(joints) if j != i]
        if not tr:  # n=1 impossible
            continue
        w_, b_ = fit_logistic_pairs(tr)
        p = 1/(1+math.exp(-max(-30, min(30, w_*e + b_))))
        hits += int((p>=0.5)==bool(y))
    acc = hits / len(joints)
    lo, hi = wilson(hits, len(joints))
    cal = {"w": w, "b": b, "mu": base.get("mu", 0.026),
           "update_count": base.get("update_count", 0) + 1,
           "source": "mcp-recalibrated",
           "n_joints": len(joints), "loo_acc": acc, "loo_wilson95": [lo, hi]}
    CAL.write_text(json.dumps(cal, indent=1) + "\n")
    print(f"n_joints={len(joints)} positifs={n_pos} | LOO acc {acc:.3f} [{lo:.3f},{hi:.3f}]")
    print(f"→ calibration mise à jour: w={w:.3f} b={b:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
