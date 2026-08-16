#!/usr/bin/env python3
"""Story 14.4 / 13.5 — validation prospective d'advprobe sur la strate TS
(lignes JAMAIS VUES : créées après le scellement des gates 13.1).

Combinator GELÉ (13.3, jamais retouché) : projection linéaire 768→12, GRL
λ_adv=1.0 sur la famille, lr 1e-3, 300 epochs, seed 20260805, entraîné sur le
clean slice v10. Évaluation : les 14 lignes coverage-ts-1 (jamais dans v10).

Gate 13.5 : AUC ≥ 0.5977 sur ces lignes. Pré-déclaré dans la fenêtre
coverage-ts-v1 : si une classe est vide, la gate est DÉGÉNÉRÉE (AUC indéfinie),
rapportée comme telle + diagnostic descriptif (distribution des scores vs
seuil) — jamais un chiffre inventé.
Run: uv run --package li-probe --extra ml python scripts/act3/advprobe_prospective_ts.py
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
OUT = ROOT / "governance" / "act2" / "arm-artifacts" / "advprobe-prospective-ts-2026-08-16.json"

for name, path in (("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py"),
                   ("advp", ROOT / "scripts" / "act3" / "probe_adversarial.py")):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
s11, advp = sys.modules["s11"], sys.modules["advp"]


def main() -> int:
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"

    rows10 = json.loads((PILOT / "latent-pool-v10.json").read_text())
    d10 = np.load(PILOT / "latent-pool-v10.npz")
    idx = [i for i, r in enumerate(rows10) if not r.get("goal_free")]
    slice10 = [rows10[i] for i in idx]
    cd10 = s11.norm(s11.norm(d10["E_state"]) + s11.norm(d10["E_diff"]))[idx]
    y10 = np.array([int(r["y"]) for r in slice10])
    fam10 = np.array([advp.family_of(r["task"]) for r in slice10])

    ts_rows = json.loads((PILOT / "coverage-ts-1" / "coverage-ts-1-rows.json").read_text())
    dts = np.load(PILOT / "coverage-ts-1" / "coverage-ts-1-embed.npz")
    cd_ts = s11.norm(s11.norm(dts["E_state"]) + s11.norm(dts["E_diff"]))
    y_ts = np.array([int(r["y"]) for r in ts_rows])

    # entraînement GELÉ : identique à 13.3 (substrat v10, mêmes hyperparams)
    enc, head = advp.train_probe(cd10, y10, fam10, device)
    with torch.no_grad():
        Xtr = torch.as_tensor(cd10, dtype=torch.float32, device=device)
        thr = float(torch.median(head(enc(Xtr))[:, 1]).item())
        s_ts = head(enc(torch.as_tensor(cd_ts, dtype=torch.float32,
                                        device=device)))[:, 1].cpu().numpy()
    pred = (s_ts > thr).astype(int)

    n_pos, n_neg = int((y_ts == 1).sum()), int((y_ts == 0).sum())
    if n_pos == 0 or n_neg == 0:
        auc_val = float("nan")
        gate = ("DÉGÉNÉRÉE — classe manquante sur la population prospective "
                "(quota TS mono-classe positive) ; AUC indéfinie, règle scellée "
                "« indéfini ≠ conforme »")
    else:
        auc_val = s11.auc(s_ts[y_ts == 1], s_ts[y_ts == 0])
        gate = "FRANCHIE (≥0.5977)" if auc_val >= 0.5977 else "non franchie"

    report = {
        "story": "13.5-validation-prospective / 14.4",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "device": device,
        "candidate": "advprobe (combinator gelé 13.3 : h=12, λ=1, lr=1e-3, "
                     "300 epochs, seed 20260805, entraîné sur clean slice v10)",
        "prospective_population": {"source": "coverage-ts-1 (fenêtre 14, créée "
                                             "APRÈS le scellement des gates 13.1)",
                                   "n": len(y_ts),
                                   "positives": n_pos, "negatives": n_neg},
        "gate_13_5": {"metric": "AUC sur scores tête-classifieur",
                      "threshold": 0.5977},
        "auc": None if math.isnan(auc_val) else round(auc_val, 4),
        "gate_status": gate,
        "descriptive_diagnostics": {
            "threshold_v10_median": round(thr, 4),
            "ts_predits_positifs": int(pred.sum()),
            "ts_score_min": round(float(s_ts.min()), 4),
            "ts_score_max": round(float(s_ts.max()), 4),
            "ts_score_median": round(float(np.median(s_ts)), 4),
            "note": "descriptif seulement — aucune valeur de gate n'en est "
                    "dérivée (gate dégénérée tant qu'une classe est vide)",
        },
        "verdict": "la validation prospective ne peut pas STATUER sur ce quota "
                   "mono-classe ; l'invariance famille d'advprobe sur le TS réel "
                   "deviendra statuable dès qu'un quota TS contient des échecs "
                   "groundés (mutants plus durs, ou collectes réelles)",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"advprobe sur TS prospective : {pred.sum()}/{len(y_ts)} prédits positifs "
          f"(scores {s_ts.min():.3f}..{s_ts.max():.3f}, seuil {thr:.3f})")
    print(f"gate 13.5 : {gate}")
    print(f"→ {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
