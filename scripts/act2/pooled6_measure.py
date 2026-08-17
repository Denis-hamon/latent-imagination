#!/usr/bin/env python3
"""NIGHT-HARVEST-v1 — mesure pooled6 (jina) : poison ext-LOAO + AUC/IC
bootstrap + breakdown par famille-auteur. Même protocole que pooled4/sweep.
Run: uv run python scripts/act2/pooled6_measure.py
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
P5 = PILOT / "pooled6"
_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)


def main() -> int:
    rows = json.loads((P5 / "pooled6-rows.json").read_text())
    d = np.load(P5 / "pooled6-embed.npz")
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    cd = s11.norm(d["E_diff"].astype(np.float32))
    f1 = s11._loao_f1_features(cd, tasks, y)
    pos, neg = f1[y == 1], f1[y == 0]
    auc = s11.auc(pos, neg)
    rng = np.random.default_rng(20260816)
    aucs = np.array([s11.auc(rng.choice(pos, len(pos), replace=True),
                             rng.choice(neg, len(neg), replace=True)) for _ in range(2500)])
    lo, hi = np.percentile(aucs, [2.5, 97.5])
    verdict = "PASS" if (auc >= 0.65 and min(int((y == 1).sum()), int((y == 0).sum())) >= 5) else "POISON/DÉGÉNÉRÉ"
    # breakdown auteur
    by_author = {}
    for r in rows:
        if r.get("campaign") == "night-harvest-v1":
            a = (r.get("author") or "?").split("/")[0][:24]
            st = by_author.setdefault(a, [0, 0])
            st[r["y"]] += 1
    report = {"population": "pooled6", "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
              "n": len(rows), "pos": int((y == 1).sum()), "neg": int((y == 0).sum()),
              "encoder": "jina-v2-base-code", "auc_ext_loao": round(float(auc), 4),
              "ic95": [round(float(lo), 4), round(float(hi), 4)],
              "p_below_0_60": round(float(np.mean(aucs < 0.60)), 4),
              "gate_0_65": verdict,
              "harvest_par_auteur": {k: {"pos": v[1], "neg": v[0]} for k, v in by_author.items()},
              "controle_pooled4_unixcoder_rappel": {"auc": 0.6951, "ic95": [0.5954, 0.7930]},
              "controle_pooled4_jina_rappel": {"auc": 0.7428, "ic95": [0.6402, 0.8402]}}
    (ROOT / "governance" / "act2" / "arm-artifacts" /
     f"pooled6-measure-{datetime.now(UTC).strftime('%Y-%m-%d-%H%M')}.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"POOLED5: n={len(rows)} ({report['pos']}+/{report['neg']}-) AUC={auc:.4f} IC95=[{lo:.4f},{hi:.4f}] p(<0.60)={np.mean(aucs<0.60):.3f} => {verdict}")
    for k, v in by_author.items():
        print(f"  {k}: pos={v[1]} neg={v[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
