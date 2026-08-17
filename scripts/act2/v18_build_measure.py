#!/usr/bin/env python3
"""Fenêtre v18 (dd454c56) — pool TS réel axe goal : embed + A1 reproduction +
A2/A3 poison recette pooled6 + A4 conformal descriptif + sauvegarde pool.
Node GPU. Run: .venv/bin/python scripts/act2/v18_build_measure.py <v18-rows.json>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ALPHA, N_MIN = 0.10, 12
_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)


def main() -> int:
    rows = json.loads(Path(sys.argv[1]).read_text())
    cache = Path(sys.argv[1]).with_suffix(".emb.npz")
    y = np.array([r["y"] for r in rows])
    tasks = np.array([r["task"] for r in rows])
    if cache.is_file():
        d = np.load(cache)
        Es, Ed, Eg = d["Es"], d["Ed"], d["Eg"]
        print("cache embeddings OK", flush=True)
    else:
        sys.path.insert(0, str(Path(__file__).parent))
        from v17_measure import embed_node
        Es = embed_node([r["state"] for r in rows])
        Ed = embed_node([r["diff"][:8000] for r in rows])
        Eg = embed_node([r["gold"][:8000] for r in rows])
        np.savez_compressed(cache, Es=Es, Ed=Ed, Eg=Eg)
        print("embeddings calculés", flush=True)

    def goal_auc_on(ix):
        yy, tt = y[ix], tasks[ix]
        cd = s11.norm(s11.norm(Es[ix]) + s11.norm(Ed[ix]))
        cg = s11.norm(s11.norm(Es[ix]) + s11.norm(Eg[ix]))
        _, _, sco = s11.loao_energy(cd, cg, yy, tt)
        return sco, s11.auc(sco[yy == 1], sco[yy == 0])

    # ---- A1 reproduction : sous-ensemble v17 (312 clés) ----
    v17keys = set()
    v17f = ROOT / "data" / "landing" / "act2-pilot" / "ts-gold-v17" / "v17-rows.json"
    if v17f.is_file():
        v17keys = {r["key"] for r in json.loads(v17f.read_text())}
    ix17 = np.array([i for i, r in enumerate(rows) if r["key"] in v17keys])
    _sco17, auc17 = goal_auc_on(ix17)
    a1_ok = abs(auc17 - 0.7408) <= 0.01
    print(f"A1 reproduction v17 (n={len(ix17)}) : AUC goal {auc17:.4f} "
          f"(attendu 0.7408 ±0.01) -> {'OK' if a1_ok else 'DÉRIVE'}", flush=True)

    # ---- A2/A3 population complète : axe goal, recette loao_energy + poison pooled6 ----
    sco, auc_goal = goal_auc_on(np.arange(len(rows)))
    rng = np.random.default_rng(20260817)
    posg, negg = sco[y == 1], sco[y == 0]
    aucs = np.array([s11.auc(rng.choice(posg, len(posg), replace=True),
                             rng.choice(negg, len(negg), replace=True)) for _ in range(2500)])
    lo, hi = np.percentile(aucs, [2.5, 97.5])
    minclass = min(int((y == 1).sum()), int((y == 0).sum()))
    gate = auc_goal >= 0.65 and minclass >= 5
    # descriptif : cd-only même recette LOAO-f1
    cd = s11.norm(s11.norm(Es) + s11.norm(Ed))
    f1 = s11._loao_f1_features(cd, tasks, y)
    auc_cd = s11.auc(f1[y == 1], f1[y == 0])
    print(f"A2/A3 : AUC goal {auc_goal:.4f} IC95 [{lo:.4f},{hi:.4f}] "
          f"AUC cd {auc_cd:.4f} poison={'PASS' if gate else 'FAIL'}", flush=True)

    # ---- A4 conformal descriptif (α=0.10, strates = repo) ----
    cg = s11.norm(s11.norm(Es) + s11.norm(Eg))
    pred, conf, _ = s11.loao_energy(cd, cg, y, tasks)
    errors = pred != y
    strata = {}
    for g in sorted({t.split("__")[0] for t in tasks}):
        idx = np.array([t.startswith(g + "__") for t in tasks])
        n = int(idx.sum())
        if n < N_MIN:
            strata[g] = {"n": n, "tau": None, "kept": 0, "realized_err_rate": None,
                         "garantie": f"n<{N_MIN} : abstention"}
            continue
        c, e = conf[idx], errors[idx]
        tau = float(np.quantile(c, np.ceil((n + 1) * (1 - ALPHA)) / n, method="higher")) \
            if np.ceil((n + 1) * (1 - ALPHA)) <= n else float(c.max())
        kept = c >= tau
        strata[g] = {"n": n, "tau": round(tau, 6), "kept": int(kept.sum()),
                     "coverage": round(float(kept.mean()), 4),
                     "realized_err_rate": round(float(e[kept].mean()), 4) if kept.sum() else None}
    print("A4 conformal :", json.dumps(strata, ensure_ascii=False), flush=True)

    # ---- sauvegarde pool v18 ----
    out_json = ROOT / "data" / "landing" / "act2-pilot" / "latent-pool-v18.json"
    out_npz = ROOT / "data" / "landing" / "act2-pilot" / "latent-pool-v18.npz"
    pools = [{
        "task": r["task"], "arm": "v18-ts-gold", "campaign": "harvest-reel-gold",
        "state": r["state"], "gold": r["gold"], "diff": r["diff"], "y": int(r["y"]),
        "encoder": "jina-v2-base-code", "goal_free": False, "source_key": r["key"],
        "window": "ts-pool-goal-v18", "origin": r.get("window")} for r in rows]
    out_json.write_text(json.dumps(pools, indent=1, ensure_ascii=False) + "\n")
    np.savez_compressed(out_npz, E_state=Es.astype(np.float32),
                        E_diff=Ed.astype(np.float32), E_goal=Eg.astype(np.float32))

    a2_ok = auc_goal >= 0.70 and lo >= 0.65
    verdict = "PROMOUVABLE" if (a1_ok and a2_ok and gate) else "NON PROMOUVABLE"
    report = {"window": "v18-ts-pool-goal", "anchor": "dd454c567217d716",
              "population_sha16": "cd0000452c37aef5",
              "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
              "population": {"n": len(rows), "pos": int((y == 1).sum()),
                             "neg": int((y == 0).sum()), "tickets": len(set(tasks))},
              "A1_reproduction_v17": {"n": len(ix17), "auc_goal": round(float(auc17), 4),
                                      "attendu": [0.7308, 0.7508], "ok": bool(a1_ok)},
              "A2_auc_goal_full": {"auc": round(float(auc_goal), 4),
                                   "ic95_bootstrap2500": [round(float(lo), 4), round(float(hi), 4)],
                                   "grille": ">=0.70 ET IC bas >=0.65", "ok": bool(a2_ok)},
              "A3_poison_recette_pooled6": {"gate_0_65": bool(gate), "min_classe": minclass,
                                            "auc_descriptif_cd_only": round(float(auc_cd), 4)},
              "A4_conformal_descriptif": strata,
              "pool": {"json": str(out_json.name), "npz": str(out_npz.name),
                       "goal_free": False},
              "verdict": verdict,
              "question_serving_owner": ("qui consomme l'axe goal ? candidate : assess_patch "
                                         "(accepte déjà goal_text) ; risk_scan reste goal-free "
                                         "par construction. Aucune modification serving dans v18.")}
    art = ROOT / "governance" / "act2" / "arm-artifacts" / "window-v18-pool-goal-mesure-2026-08-17.json"
    art.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
