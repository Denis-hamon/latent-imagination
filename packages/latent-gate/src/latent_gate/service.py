"""Couche service partagée par les deux transports (MCP stdio, HTTP FastAPI).

Toutes les décisions produit y vivent une seule fois :
- le diff est scoré TEL QU'ÉMIS (jamais sanitize — recovered = poison, 08-10g)
- abstention = tier de confiance issu des quantiles OOF
- goal_text absent → retour explicite "goal-free only" (G1 : but emprunté = mort,
  on ne fabrique pas de but)
- report_outcome : append-only, hashé, NE MUTE JAMAIS le pool en ligne
- exclude_task : filtre le pool avant tout score (falsifiabilité publique LOAO)
"""

from __future__ import annotations

import json
import os
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import encoder
from .pool import get_pool
from .scoring import GateModel, energy_gold, f1_attractor

OUTCOME_DIR = Path(os.environ.get(
    "LI_OUTCOME_DIR",
    # src/latent_gate/service.py → parents[4] = racine du repo latent-imagination
    Path(__file__).resolve().parents[4] / "data" / "landing" / "mcp-outcomes"))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _log_outcome(entry: dict):
    OUTCOME_DIR.mkdir(parents=True, exist_ok=True)
    f = OUTCOME_DIR / (time.strftime("%Y-%m-%d", time.gmtime()) + ".jsonl")
    with f.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def score_patch(state_text: str, diff_text: str, goal_text: str | None = None,
                exclude_task: str | None = None) -> dict:
    """Le tool central. Jamais de verdict sans tier de confiance."""
    t0 = time.time()
    pool = get_pool()
    model = GateModel()

    e_s = encoder.embed_one(state_text[:4000])
    e_d = encoder.embed_one(diff_text[:4000])
    cd_q = e_s + e_d
    cd_q = cd_q / (np.linalg.norm(cd_q) + 1e-9)

    keep = pool.comask(exclude_task)
    f1 = f1_attractor(cd_q, pool.cd, pool.y, keep)

    out: dict = {"call_id": sha256(
        f"{t0}:{state_text[:80]}:{diff_text[:80]}".encode()).hexdigest()[:12],
        "attractor_score": round(f1, 4),
        "model_sha": model.sha256[:16],
        "recipe": model.recipe}

    if goal_text:
        e_g = encoder.embed_one(goal_text[:4000])
        energy = energy_gold(e_s, e_d, e_g)
        p, conf, tier = model.combine(energy, f1)
        if tier == "low":
            advice = "abstain"
        elif p > 0.5:
            advice = "likely-pass" if tier == "high" else "lean-pass"
        else:
            advice = "likely-fail" if tier == "high" else "lean-fail"
        out.update({
            "energy": round(energy, 4),
            "p_pass": round(p, 3),
            "confidence": round(conf, 4),
            "confidence_tier": tier,
            "advice": advice,
        })
    else:
        # G1 mesuré : un but emprunté ne transfère pas — on ne fabrique rien
        out.update({
            "advice": "goal-free-only",
            "note": "fournissez goal_text (énoncé de tests / problème) pour le "
                    "score GOLD ; sans but, seul le risk-axes survit (rang, pas verdict)",
            "zone": "high_risk" if f1 < 0 else "low_risk"})
    _log_outcome({"ts": _now(), "type": "score", "call_id": out["call_id"],
                  "advice": out["advice"],
                  "state_sha": sha256(state_text.encode()).hexdigest()[:16],
                  "diff_sha": sha256(diff_text.encode()).hexdigest()[:16],
                  "exclude_task": exclude_task, "latency_s": round(time.time() - t0, 3)})
    return out


def risk_scan(state_text: str, diff_text: str, exclude_task: str | None = None) -> dict:
    pool = get_pool()
    e_s = encoder.embed_one(state_text[:4000])
    e_d = encoder.embed_one(diff_text[:4000])
    cd_q = e_s + e_d
    cd_q /= (np.linalg.norm(cd_q) + 1e-9)
    keep = pool.comask(exclude_task)
    f1 = f1_attractor(cd_q, pool.cd, pool.y, keep)
    cd = pool.cd if keep.all() else pool.cd[keep]
    y = pool.y if keep.all() else pool.y[keep]
    sims = cd @ cd_q
    out = {"attractor_score": round(f1, 4),
           "zone": "high_risk" if f1 < 0 else "low_risk",
           "d_nearest_fail": round(float((1 - sims[y == 0]).min()), 4) if (y == 0).any() else None,
           "d_nearest_pass": round(float((1 - sims[y == 1]).min()), 4) if (y == 1).any() else None,
           "note": "rang, pas verdict (G1, AUC 0.709 sans but)"}
    _log_outcome({"ts": _now(), "type": "risk_scan", **out})
    return out


def near_misses(state_text: str, k: int = 3,
                exclude_task: str | None = None) -> dict:
    """K voisins du pool par similarité d'ÉTAT, dédupliqués par tâche, avec
    leur issue réelle. Informer un choix, jamais rendre un verdict."""
    pool = get_pool()
    q = encoder.embed_one(state_text[:4000])
    q = q / (np.linalg.norm(q) + 1e-9)
    sims = pool.E_s @ q
    order = sims.argsort()[::-1]
    rows, seen = [], set()
    for i in order:
        r = pool.rows[int(i)]
        if r["task"] in seen or r["task"] == exclude_task:
            continue
        seen.add(r["task"])
        rows.append({"task": r["task"], "arm": r.get("arm"),
                     "y": int(r["y"]), "sim": round(float(sims[int(i)]), 4)})
        if len(rows) >= k:
            break
    _log_outcome({"ts": _now(), "type": "near_misses", "k": k,
                  "top_task": rows[0]["task"] if rows else None})
    return {"nearest": rows, "k": k}


def report_outcome(call_id: str, passed: bool) -> dict:
    _log_outcome({"ts": _now(), "type": "outcome", "call_id": call_id,
                  "passed": bool(passed)})
    return {"status": "enregistré, hashé ; promotion au pool par batch validé"}


def health() -> dict:
    pool = get_pool()
    model = GateModel()
    return {"status": "ok", "pool_n": len(pool.rows),
            "pool_sha256": pool.sha256[:16], "model_sha256": model.sha256[:16],
            "recipe": model.recipe, "version": "0.1.0"}
