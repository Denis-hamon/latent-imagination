#!/usr/bin/env python3
"""S14 extras (Mac, 0 call galere) — mesures secondaires sur le pool courant :

1. Refit LOTO du predictor GBDT v3 (features struct+hash D/P/T, stdlib) sur le
   pool le plus étendu disponible (v8 > v7 > v6) — « entraîner le modèle » sur
   les nouveaux labels ; comparé au refit v2 historique.
2. Variante multi-espaces C1 (uxc + Qwen2.5-Coder-7B-last, GxF 4 features
   λ=2, LOAO-strict) si l'npz Qwen complet du pool existe — l'instrument qui
   valait 0.856 sur v6, jamais re-mesuré depuis S11.
3. Statistiques descriptives par campagne.

Sortie : data/landing/act2-pilot/s14-extras.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "act2" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _task_meta():
    meta = {}
    for tj in (PILOT / "pilot-tasks-frozen32.json", PILOT / "pilot-tasks.json",
               PILOT / "extension-128" / "pilot-tasks.json",
               PILOT / "pilot-tasks-full.json"):
        if tj.is_file():
            for t in json.loads(tj.read_text()):
                if isinstance(t, dict) and "instance_id" in t:
                    meta.setdefault(t["instance_id"], t)
    return meta


def gbdt_loto(rows: list[dict]) -> dict:
    rp = _load("refit_predictor_v3_gbdt")
    tmeta = _task_meta()
    samples, no_meta = [], 0
    for r in rows:
        t = (tmeta.get(r["task"])
             or tmeta.get(r["task"].replace("__", "/", 1)))
        if t is None:
            no_meta += 1
            continue
        samples.append({"task": r["task"], "y": int(r["y"]),
                        "x": rp.featurize_v3(r["diff"], t.get("problem", ""),
                                             t.get("f2p") or [])})
    tasks = sorted({s["task"] for s in samples})
    tp = tn = fp = fn = 0
    for t in tasks:
        tr = [(s["x"], s["y"]) for s in samples if s["task"] != t]
        te = [s for s in samples if s["task"] == t]
        m = rp.fit_gbdt([x for x, _ in tr], [y for _, y in tr])
        for s in te:
            p = rp.predict_gbdt(m, s["x"])
            hyp = p >= 0.5
            tp += hyp and s["y"]; tn += not hyp and not s["y"]
            fp += hyp and not s["y"]; fn += not hyp and s["y"]
    n = tp + tn + fp + fn
    return {"n": n, "tasks": len(tasks), "sans_meta": no_meta,
            "accuracy": (tp + tn) / max(1, n),
            "lo,hi": rp.wilson(tp + tn, n),
            "majority": max(tp + fn, tn + fp) / max(1, n),
            "recall_pos": tp / max(1, tp + fn),
            "precision_pos": tp / max(1, tp + fp),
            "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn}}


def c1_multispace(rows, du, dq, s11) -> dict:
    norm, loao_energy = s11.norm, s11.loao_energy
    logreg_fit = _load("s10_scamper").logreg_fit
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    maj = max(y.mean(), 1 - y.mean())
    EU = {k: norm(du[k]) for k in ("E_state", "E_diff", "E_goal")}
    EQ = {k: norm(dq[k]) for k in ("E_state", "E_diff", "E_goal")}
    cdU, cgU = norm(EU["E_state"] + EU["E_diff"]), norm(EU["E_state"] + EU["E_goal"])
    cdQ, cgQ = norm(EQ["E_state"] + EQ["E_diff"]), norm(EQ["E_state"] + EQ["E_goal"])
    eU = 1 - (cdU * cgU).sum(-1)
    eQ = 1 - (cdQ * cgQ).sum(-1)
    n = len(y)
    pred = np.zeros(n, int); conf = np.zeros(n); sco = np.zeros(n)
    for held in sorted(set(tasks)):
        te, tr = tasks == held, tasks != held
        y_tr = y[tr]
        if not y_tr.any() or y_tr.all():
            continue

        def f1s(cdS):
            sims = cdS[te] @ cdS[tr].T
            f1_te = (1 - sims[:, y_tr == 0]).min(1) - (1 - sims[:, y_tr == 1]).min(1)
            f1_tr = ((1 - cdS[tr] @ cdS[tr][y_tr == 0].T).min(1)
                     - (1 - cdS[tr] @ cdS[tr][y_tr == 1].T).min(1))
            return f1_tr, f1_te
        f1U_tr, f1U_te = f1s(cdU)
        f1Q_tr, f1Q_te = f1s(cdQ)
        Ftr = np.column_stack([-eU[tr], f1U_tr, -eQ[tr], f1Q_tr])
        Fte = np.column_stack([-eU[te], f1U_te, -eQ[te], f1Q_te])
        mu, sd = Ftr.mean(0), Ftr.std(0) + 1e-9
        w = logreg_fit((Ftr - mu) / sd, y_tr, lam=2.0)
        Xte = np.column_stack([np.ones(te.sum()), (Fte - mu) / sd])
        p = 1.0 / (1.0 + np.exp(-(Xte @ w)))
        pred[te] = (p > 0.5).astype(int)
        conf[te] = np.abs(p - 0.5)
        sco[te] = p
    res = s11.report("C1 GxF 4 espaces v8 (λ=2)", pred, conf, sco, y, maj)
    return res


def main() -> int:
    s11 = _load("s11_ext_pool")
    # pool le plus étendu dispo
    pool = None
    for name in ("latent-pool-v8.json", "latent-pool-v7.json"):
        if (PILOT / name).is_file():
            pool = name
            break
    rows = json.loads((PILOT / pool).read_text())
    out = {"pool": pool, "n": len(rows),
           "positifs": int(sum(r["y"] for r in rows)),
           "par_campagne": {}}
    art = ROOT / "governance" / "act2" / "arm-artifacts" / "predictor-act2-v3-gbdt.json"
    if art.is_file():
        out["rappel_refit_v2"] = json.loads(art.read_text()).get("measured", {})
    import collections
    cc = collections.Counter(r.get("campaign", "?") for r in rows)
    out["par_campagne"] = {k: {"n": v, "pos": sum(1 for r in rows
                              if r.get("campaign") == k and r["y"])}
                           for k, v in sorted(cc.items())}

    print("refit GBDT v3 LOTO…", flush=True)
    out["gbdt_v3_loto"] = gbdt_loto(rows)
    print(json.dumps(out["gbdt_v3_loto"], indent=1, default=str))

    du = np.load(PILOT / pool.replace(".json", ".npz"))
    qf = PILOT / pool.replace(".json", "-qwen7b-last.npz")
    if qf.is_file():
        dq = np.load(qf)
        if dq["E_state"].shape[0] == len(rows):
            print("C1 multi-espaces…", flush=True)
            out["c1_gxf_4espaces"] = c1_multispace(rows, du, dq, s11)
        else:
            out["c1_gxf_4espaces"] = {"skip": f"qwen npz incomplet "
                                      f"({dq['E_state'].shape[0]}/{len(rows)})"}
    else:
        out["c1_gxf_4espaces"] = {"skip": "pas d'npz Qwen pour ce pool"}

    (PILOT / "s14-extras.json").write_text(json.dumps(out, indent=1, default=float))
    print(f"OK {PILOT / 's14-extras.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
