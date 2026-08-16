#!/usr/bin/env python3
"""Story 13.1 — benchmark ext-LOAO : famille entièrement held-out, seuil
réappris sur train seulement (LOAO-strict, zéro fuite famille).

Métrique : score q = d(nearest FAIL train) − d(nearest PASS train) en espace cd
normalisé (la géométrie servie goal-free) ; thr = médiane des scores TRAIN
(réappris par fold — jamais le thr du pool complet) ; pred held-out = q > thr ;
AUC Mann-Whitney agrégée sur toutes les lignes évaluées sous leur fold
famille-held-out + rapport par famille. Familles à classe unique dans le pool :
l'AUC n'est définie que si les deux classes apparaissent dans l'agrégat — les
folds sans variance sont rapportés mais ne contribuent à l'AUC que par leurs
lignes (standard Mann-Whitney sur l'agrégat).

Contrôle d'intégrité : v6 GOLD energy (0.822/0.779) rejoué inchangé.
0 appel. Sortie : governance/act2/arm-artifacts/ext-loao-benchmark-v10.json
Run: uv run python scripts/act2/ext_loao.py [--pool v10]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
OUT = ROOT / "governance" / "act2" / "arm-artifacts"

_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)


def family_of(task: str) -> str:
    for sep in (".", ":"):
        if sep in task:
            return task.split(sep, 1)[0]
    return task


def ext_loao(cd: np.ndarray, y: np.ndarray, fams: np.ndarray) -> dict:
    n = len(y)
    scores = np.full(n, np.nan)
    preds = np.full(n, -1)
    fam_list = sorted(set(fams.tolist()))
    per_fam = {}
    for g in fam_list:
        te = fams == g
        tr = ~te
        if te.sum() == 0 or not y[tr].any() or y[tr].all():
            per_fam[g] = {"n": int(te.sum()), "skipped": "train sans les deux classes"}
            continue
        cd_tr, y_tr = cd[tr], y[tr]
        pos, neg = cd_tr[y_tr == 1], cd_tr[y_tr == 0]
        thr = None
        s_tr = (1 - cd_tr @ neg.T).min(1) - (1 - cd_tr @ pos.T).min(1)
        thr = float(np.median(s_tr))  # seuil réappris SUR TRAIN uniquement
        S_te = cd[te]
        q = (1 - S_te @ neg.T).min(1) - (1 - S_te @ pos.T).min(1)
        scores[te] = q
        preds[te] = (q > thr).astype(int)
        k = int(te.sum())
        per_fam[g] = {"n": k, "n_pos": int(y[te].sum()),
                      "acc": round(float((preds[te] == y[te]).mean()), 4),
                      "held_out_thr": round(thr, 6)}
    valid = ~np.isnan(scores)
    auc = s11.auc(scores[valid][y[valid] == 1], scores[valid][y[valid] == 0])
    acc = float((preds[valid] == y[valid]).mean())
    return {"auc_ext_loao": round(auc, 4), "acc_ext_loao": round(acc, 4),
            "n_evaluated": int(valid.sum()), "n_families": len(fam_list),
            "per_family": per_fam,
            "discipline": "famille entièrement held-out ; seuil = médiane des "
                          "scores du TRAIN de chaque fold (jamais le pool complet)"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="v10")
    args = ap.parse_args()
    pool = args.pool

    # contrôle v6 GOLD (machinerie intacte — recette inchangée des promotions)
    rows6 = json.loads((PILOT / "latent-pool-v6.json").read_text())
    d6 = np.load(PILOT / "latent-pool-v6.npz")
    y6 = np.array([int(r["y"]) for r in rows6])
    t6 = np.array([r["task"] for r in rows6])
    Es6, Ed6, Eg6 = (s11.norm(d6[k]) for k in ("E_state", "E_diff", "E_goal"))
    pred6, conf6, sco6 = s11.loao_energy(s11.norm(Es6 + Ed6), s11.norm(Es6 + Eg6), y6, t6)
    ctrl = s11.report("CTRL v6 GOLD", pred6, conf6, sco6, y6,
                      max(y6.mean(), 1 - y6.mean()))
    ctrl_ok = abs(ctrl["auc"] - 0.822) < 0.01 and abs(ctrl["acc100"] - 0.779) < 0.005
    print(f"[ctrl v6] AUC {ctrl['auc']:.3f} acc100 {ctrl['acc100']:.3f} → "
          f"{'OK' if ctrl_ok else 'DÉRIVE'}")

    rows = json.loads((PILOT / f"latent-pool-{pool}.json").read_text())
    d = np.load(PILOT / f"latent-pool-{pool}.npz")
    y = np.array([int(r["y"]) for r in rows])
    tasks = [r["task"] for r in rows]
    fams = np.array([family_of(t) for t in tasks])
    cd = s11.norm(s11.norm(d["E_state"]) + s11.norm(d["E_diff"]))
    bench = ext_loao(cd, y, fams)

    # in-family LOAO co-rapporté (le home regime de référence)
    f1_in = s11._loao_f1_features(cd, np.array(tasks), y)
    thr_in = float(np.median(f1_in))
    acc_in = float(((f1_in > thr_in).astype(int) == y).mean())
    auc_in = s11.auc(f1_in[y == 1], f1_in[y == 0])

    report = {
        "story": "13.1-ext-loao-benchmark",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "pool": f"latent-pool-{pool}.json",
        "pool_sha256_16": sha256(
            (PILOT / f"latent-pool-{pool}.json").read_bytes()).hexdigest()[:16],
        "n_rows": len(rows), "positives": int(y.sum()),
        "v6_gold_control": {"auc": round(ctrl["auc"], 3),
                            "acc100": round(ctrl["acc100"], 3),
                            "expected": [0.822, 0.779], "ok": bool(ctrl_ok)},
        "baseline_current_instrument": {
            "ext_loao": bench,
            "in_family_loao": {"auc": round(auc_in, 4), "acc": round(acc_in, 4),
                               "note": "propre famille exclue des voisins mais pas "
                                       "held-out (régime de référence servi)"},
            "reference_s14_ext_unseen": 0.750,
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"ext-loao-benchmark-{pool}.json"
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"ext-LOAO {pool}: AUC {bench['auc_ext_loao']} acc {bench['acc_ext_loao']} "
          f"({bench['n_evaluated']} lignes évaluées, {bench['n_families']} familles) — "
          f"réf S14 unseen 0.750")
    print(f"in-family LOAO: AUC {auc_in:.4f} acc {acc_in:.4f}")
    print(f"→ {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
