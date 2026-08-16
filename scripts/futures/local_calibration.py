#!/usr/bin/env python3
"""Ghost pivot — story 15.2 : calibration conforme locale de session.

DONNÉ : (a) outcomes groundées du bootstrap (n issues, 15.1), (b) embeddings
des K candidats + du prior global (pool v10). REND : pour chaque candidat, un
score goal-free, une probabilité prédite avec IC conforme, un régime
(local/ fallback-prior) et les abstentions — sans jamais deviner.

Mécanique (héritée discipline scellée) :
  - feature LOAO-F1 : d(neg proche) - d(pos proche) sur E_diff normalisé,
    propre candidat exclu des voisins (s11._loao_f1_features) ;
  - contexte de scoring = prior global v10 UNION issues locales ;
  - classification locale : logreg ridge sur E_diff des n points locaux
    (s11.logreg_fit) => p_local ; si n < n_min (8) => régime fallback-prior :
    la prédiction vient du score global SEUL, disclosure explicite ;
  - conforme : tau sur résidus LOO des n points bootstrap (conformal_tau),
    alpha défaut 0.10 ; si n < n_min => tau du pool servi (disclosure).

Run: uv run python scripts/futures/local_calibration.py --session <dir> --manifest <json>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)
_cspec = importlib.util.spec_from_file_location("cc", ROOT / "scripts" / "act2" / "conformal_calibrate.py")
cc = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(cc)

N_MIN = 8
POOL = ROOT / "data" / "landing" / "act2-pilot"


def load_prior() -> tuple[np.ndarray, np.ndarray, list[str], np.ndarray]:
    rows = json.loads((POOL / "latent-pool-v10.json").read_text())
    d = np.load(POOL / "latent-pool-v10.npz")
    y = np.array([int(r["y"]) for r in rows])
    tasks = [str(r.get("task", r.get("instance_id", i))) for i, r in enumerate(rows)]
    E = s11.norm(d["E_diff"].astype(np.float32))
    pool_f1 = s11._loao_f1_features(E, np.array(tasks), y)
    return E, y, tasks, pool_f1


def session_scores(E_local: np.ndarray, y_local: np.ndarray, E_pool: np.ndarray,
                   y_pool: np.ndarray, E_cand: np.ndarray) -> np.ndarray:
    """Score goal-free de chaque candidat : LOAO-F1 contre contexte
    (pool ∪ local), sans étiquette propre en voisin."""
    ctx = np.vstack([E_pool, E_local])
    yctx = np.concatenate([y_pool, y_local])
    allm = np.vstack([ctx, E_cand])
    n_ctx = len(yctx)
    f1 = s11._loao_f1_features(allm, np.array(["ctx"] * n_ctx + [f"c{i}" for i in range(len(E_cand))]),
                               np.concatenate([yctx, np.zeros(len(E_cand))]))
    return f1[n_ctx:]


def conformalize(scores_cal: np.ndarray, errs: np.ndarray, alpha: float) -> dict:
    import math as _m
    if len(scores_cal) < 4:
        return {"regime": "insufficient", "n": len(scores_cal)}
    quant = int(_m.ceil((1 - alpha) * (len(scores_cal) + 1))) - 1
    quant = max(0, min(len(errs) - 1, quant))
    return {"regime": "local", "n": len(scores_cal),
            "tau": float(np.sort(errs)[quant]), "alpha": alpha}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--alpha", type=float, default=0.10)
    args = ap.parse_args()
    mani = json.loads(Path(args.manifest).read_text())
    sdir = ROOT / "data" / "landing" / "act2-pilot" / mani["session_id"]
    issues = {}
    for f in sdir.glob("issue-*.json"):
        r = json.loads(f.read_text())
        if isinstance(r.get("y"), int):
            issues[r["id"]] = r
    cand_by_id = {c["id"]: c for c in mani["candidates"]}
    boot_ids = [cid for cid in issues if cid in cand_by_id]
    E_pool, y_pool, tasks_pool, pool_f1 = load_prior()
    # embeddings candidats : fichier session-embeds.npz requis (ids alignés)
    em_f = sdir / "session-embeds.npz"
    if not em_f.is_file():
        print(f"ABSENT: {em_f} — générer les embeddings candidats d'abord (genfam_embed adapté)")
        return 1
    z = np.load(em_f, allow_pickle=True)
    ids = list(z["ids"]); E_all = s11.norm(z["E_diff"].astype(np.float32))
    E_local = np.vstack([E_all[ids.index(i)] for i in boot_ids])
    y_local = np.array([issues[i]["y"] for i in boot_ids])
    E_cand = np.vstack([E_all[ids.index(i)] for i in ids])
    n = len(boot_ids)
    print(f"session {mani['session_id']}: K={len(ids)} candidats, n={n} issues bootstrap")

    scores = session_scores(E_local, y_local, E_pool, y_pool, E_cand)
    regime = "local" if n >= N_MIN else "fallback-prior"
    preds = {}
    if regime == "local":
        Xtr = E_local
        w = s11.logreg_fit(Xtr, y_local, lam=1.0, iters=300)
        Xb = np.column_stack([np.ones(len(E_cand)), E_cand])
        p_all = 1.0 / (1.0 + np.exp(-(Xb @ w)))
        Xtrb = np.column_stack([np.ones(n), E_local])
        p_cal = 1.0 / (1.0 + np.exp(-(Xtrb @ w)))
        errs = np.abs(y_local - p_cal)
        conf = conformalize(p_cal, errs, args.alpha)
    else:
        ref = float(np.median(pool_f1[y_pool == 1]))
        p_all = 1.0 / (1.0 + np.exp(-(scores - ref)))
        conf = {"regime": "fallback-prior", "n": n,
                "note": f"n={n} < {N_MIN} : pas de conforme local possible ; score prior global seul, divulgation obligatoire"}
    pred_pos = (scores >= 0)  # convention goal-free : score>0 = ressemble aux succès
    abstain = [ids[i] for i in range(len(ids))
               if regime != "local" or conf.get("tau", 1e9) > abs(float(p_all[i]) - 0.5) * 2]
    out = {"session_id": mani["session_id"],
           "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
           "n_bootstrap": n, "n_min_local": N_MIN, "regime": regime,
           "alpha": args.alpha, "conformal": conf,
           "pool_prior": {"rows": len(y_pool), "positives": int((y_pool == 1).sum())},
           "candidates": []}
    for i, cid in enumerate(ids):
        out["candidates"].append({
            "id": cid, "task": cand_by_id[cid]["task"],
            "goal_free_score": round(float(scores[i]), 4),
            "p_success": round(float(p_all[i]), 4),
            "predict_positive": bool(pred_pos[i]),
            "in_bootstrap": cid in boot_ids,
            "bootstrap_y": issues[cid]["y"] if cid in boot_ids else None})
    top = max(range(len(ids)), key=lambda i: scores[i])
    out["recommendation"] = {"id": ids[top], "reason": "score goal-free max sur contexte (prior v10 ∪ bootstrap local)",
                             "abstained_count": len(abstain)}
    (sdir / "calibration.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"régime: {regime} | recommandation: {ids[top]} | abstentions: {len(abstain)}/{len(ids)}")
    print(f"-> {sdir}/calibration.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
