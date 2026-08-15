#!/usr/bin/env python3
"""S14-pool — pool v8 : v7 + patchs générés fenêtre s14-gen (autonomie 8h).

Mêmes règles que s12_pool.py (v7) : appliqué ∧ compile ; y=1 ssi f2p ∧
(p2p ok ou non déclaré) ; dédup sha256(diff) contre TOUT le pool de base ;
state/gold repris de la ligne de base de la même tâche (ou meta tâche).
Stages : --stage pool | embed (node GPU, uxc-base CLS-512 bit-identique) |
eval (LOAO-strict : contrôle v6 0.822/0.779, rappel v7, v8 GOLD + GxF
strict, queue par provenance v6/s12/s14, gate v2 pré-déclarée inchangée).
CE SCRIPT NE PROMEUT RIEN — canonique reste v6, décision owner.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import operator
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
RESULTS_SOURCES = [PILOT / "s12-gen" / "results",   # slots récupérés par
                   PILOT / "s14-gen" / "results"]   # ré-extraction 2026-08-15
RESULTS = PILOT / "s14-gen" / "results"
BASE_JSON = PILOT / "latent-pool-v7.json"
BASE_NPZ = PILOT / "latent-pool-v7.npz"
V8_JSON = PILOT / "latent-pool-v8.json"
V8_NPZ_NEW = PILOT / "s14-new-embed.npz"
V8_NPZ = PILOT / "latent-pool-v8.npz"
S14_MODEL = "MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-bf16"

_spec = importlib.util.spec_from_file_location(
    "s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s11)
norm, wilson, auc = s11.norm, s11.wilson, s11.auc
loao_energy, gxf_loao, report = s11.loao_energy, s11.gxf_loao, s11.report


def _base():
    rows = json.loads(BASE_JSON.read_text())
    dn = np.load(BASE_NPZ)
    return rows, dn


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


def _gold_for(key: str) -> str:
    for d in (PILOT / "control-gold" / key,
              PILOT / "extension-128" / "control-gold" / key):
        g = d / "gold.diff"
        if g.is_file():
            return g.read_text()
    return ""


def stage_pool() -> int:
    rows_b, _ = _base()
    bytask = {}
    for r in rows_b:
        bytask.setdefault(r["task"], r)
    existing_pre, existing_keys = None, set()
    if V8_JSON.is_file():
        cand_ex = json.loads(V8_JSON.read_text())
        if len(cand_ex) >= len(rows_b) and cand_ex[:len(rows_b)] == rows_b:
            existing_pre = cand_ex
            for r in cand_ex[len(rows_b):]:
                bytask.setdefault(r["task"], r)
                existing_keys.add((r["task"], r.get("arm")))
    tmeta = _task_meta()
    seen = {hashlib.sha256(r["diff"].strip().encode()).hexdigest()
            for r in (existing_pre or rows_b)}
    new, skipped = [], []
    run_results = sorted(functools.reduce(operator.iadd, (list(d.glob("*/run-result.json"))
                              for d in RESULTS_SOURCES), []),
                         key=lambda p: str(p))
    for rr in run_results:
        if rr.parent.name.startswith("smoke-"):
            continue
        res = json.loads(rr.read_text())
        task = res["task"]
        arm = rr.parent.name.rsplit("-", 1)[-1]
        if (task, arm) in existing_keys:
            continue  # déjà dans le pool (vague précédente)
        if not res.get("patch_applied"):
            skipped.append((task, res.get("error") or "non-applicable"))
            continue
        if res.get("py_compiles") is False:
            skipped.append((task, "ne-compile-pas"))
            continue
        f2p = bool(res.get("f2p_pass"))
        p2p_ok = res.get("p2p_pass", True)
        y = 1 if (f2p and p2p_ok) else 0
        key = task.replace("/", "_")
        ref = bytask.get(task)
        if ref is not None:
            state, gold = ref["state"], ref["gold"]
        else:
            t = tmeta.get(task)
            if t is None:
                skipped.append((task, "tâche hors base et sans meta"))
                continue
            state = (str(t.get("problem", ""))[:1200] + "\n"
                     + "; ".join(map(str, (t.get("f2p") or [])[:6])))
            gold = _gold_for(key)
            if not gold:
                skipped.append((task, "gold introuvable"))
                continue
        diff = (rr.parent / "patch.diff").read_text()
        h = hashlib.sha256(diff.strip().encode()).hexdigest()
        if h in seen:
            skipped.append((task, f"dédup {rr.parent.name}"))
            continue
        seen.add(h)
        new.append({
            "task": task, "arm": arm,
            "campaign": "s14-gen", "author": S14_MODEL,
            "state": state, "diff": diff, "gold": gold, "y": y,
        })
    if existing_pre is not None:
        v8 = existing_pre + new
    else:
        v8 = rows_b + new
    out = {
        "n_base": len(rows_b), "n_new": len(new), "n_v8": len(v8),
        "positifs_v8": sum(r["y"] for r in v8),
        "new_positifs": sum(r["y"] for r in new),
        "taches_v8": len({r["task"] for r in v8}),
        "skipped": len(skipped), "skipped_detail": skipped[:50],
    }
    V8_JSON.write_text(json.dumps(v8, indent=1))
    (PILOT / "s14-pool-build.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items()
                      if k != "skipped_detail"}, indent=1))
    print(f"OK {V8_JSON} ({len(v8)} lignes)")
    return 0


def stage_embed() -> int:
    import os
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    import torch
    from transformers import AutoModel, AutoTokenizer

    rows_b, dn_b = _base()
    v8 = json.loads(V8_JSON.read_text())
    base_n = len(rows_b)
    if len(v8) == base_n:
        print("aucune nouvelle ligne à embarquer")
        return 0
    # reprise incrémentale : si un v8.npz existe déjà avec un préfixe au-delà de
    # la base, on n'embarque que le suffixe manquant.
    prefix, have = None, base_n
    if V8_NPZ.is_file():
        ex = np.load(V8_NPZ)
        if ex["E_state"].shape[0] >= base_n and ex["E_state"].shape[0] <= len(v8):
            prefix = {k: ex[k] for k in ("E_state", "E_diff", "E_goal")}
            have = ex["E_state"].shape[0]
    new = v8[have:]
    if not new:
        print(f"embed déjà complet ({have} lignes)")
        return 0
    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModel.from_pretrained("microsoft/unixcoder-base").to(device).eval()
    print(f"embed {len(new)} nouvelles lignes sur {device} "
          f"(préfixe existant {have})", flush=True)
    E_s = s11.batched_embed(model, tok, [r["state"] for r in new])
    E_d = s11.batched_embed(model, tok, [r["diff"] for r in new])
    E_g = s11.batched_embed(model, tok, [r["gold"] for r in new])
    np.savez_compressed(V8_NPZ_NEW, E_state=E_s, E_diff=E_d, E_goal=E_g)
    if prefix is not None and have > base_n:
        cat = {k: np.concatenate([prefix[k], d])
               for k, d in (("E_state", E_s), ("E_diff", E_d), ("E_goal", E_g))}
    else:
        cat = {k: np.concatenate([dn_b[k], d])
               for k, d in (("E_state", E_s), ("E_diff", E_d), ("E_goal", E_g))}
    np.savez_compressed(V8_NPZ, **cat)
    print(f"OK {V8_NPZ} ({cat['E_state'].shape[0]} lignes)")
    return 0


def stage_eval() -> int:
    rows6 = json.loads((PILOT / "latent-pool-v6.json").read_text())
    du6 = np.load(PILOT / "latent-pool-v6.npz")
    v8 = json.loads(V8_JSON.read_text())
    dv8 = np.load(V8_NPZ)
    y6 = np.array([int(r["y"]) for r in rows6])
    t6 = np.array([r["task"] for r in rows6])
    EU6 = {k: norm(du6[k]) for k in ("E_state", "E_diff", "E_goal")}
    pred, conf, sco = loao_energy(norm(EU6["E_state"] + EU6["E_diff"]),
                                  norm(EU6["E_state"] + EU6["E_goal"]), y6, t6)
    ctrl = report("CTRL v6 GOLD (=S7/S10/S11)", pred, conf, sco, y6,
                  max(y6.mean(), 1 - y6.mean()))
    ok = abs(ctrl["auc"] - 0.822) < 0.01 and abs(ctrl["acc100"] - 0.779) < 0.005
    print(f"  → contrôle {'OK' if ok else 'DÉRIVE — STOP'}")
    if not ok:
        return 1
    y8 = np.array([int(r["y"]) for r in v8])
    t8 = np.array([r["task"] for r in v8])
    maj8 = max(y8.mean(), 1 - y8.mean())
    camp8 = np.array([r.get("campaign") if r.get("campaign") in ("s12-gen", "s14-gen")
                      else "v6" for r in v8])
    EU8 = {k: norm(dv8[k]) for k in ("E_state", "E_diff", "E_goal")}
    cd8, cg8 = norm(EU8["E_state"] + EU8["E_diff"]), norm(EU8["E_state"] + EU8["E_goal"])
    out = {"n_v8": len(v8), "positifs_v8": int(y8.sum()),
           "majority_v8": float(maj8), "n_tasks_v8": len(set(t8)),
           "positive_control_v6": {"expected": [0.822, 0.779],
                                   "got": [ctrl["auc"], ctrl["acc100"]],
                                   "ok": bool(ok)},
           "rappel_v7": {"gold": {"auc": 0.824, "cov": 0.25},
                          "gxf_strict": {"auc": 0.867, "cov": 0.30}},
           "variants": {}}
    pred, conf, sco = loao_energy(cd8, cg8, y8, t8)
    out["variants"]["v8_gold"] = report("V8 GOLD uxc", pred, conf, sco, y8, maj8)
    pred_g, conf_g, sco_g = gxf_loao(cd8, cg8, y8, t8)
    out["variants"]["v8_gxf_strict"] = report("V8 GxF strict", pred_g, conf_g,
                                              sco_g, y8, maj8)
    order = np.argsort(-conf_g)
    m = max(1, round(len(y8) * 0.25))
    top = order[:m]
    out["queue_top25_gxf"] = {
        c: {"n": int((camp8[top] == c).sum()),
            "acc": float((pred_g[top][camp8[top] == c]
                          == y8[top][camp8[top] == c]).mean())
            if (camp8[top] == c).any() else None}
        for c in ("v6", "s12-gen", "s14-gen")}
    out["gate_v2"] = {
        "rule": "AUC>0.864 ET cov@≥0.95>30 % (pré-déclarée 2026-08-10)",
        "gold_pass": bool(out["variants"]["v8_gold"]["auc"] > 0.864
                          and out["variants"]["v8_gold"]["max_cov"] > 0.30),
        "gxf_pass": bool(out["variants"]["v8_gxf_strict"]["auc"] > 0.864
                         and out["variants"]["v8_gxf_strict"]["max_cov"] > 0.30),
        "rappel": "aucune promotion automatique — owner décide"}
    (PILOT / "s14-pool-v8-eval.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["gate_v2"], indent=1))
    print(f"\nArtefact : {PILOT / 's14-pool-v8-eval.json'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["pool", "embed", "eval"], required=True)
    a = ap.parse_args()
    return {"pool": stage_pool, "embed": stage_embed, "eval": stage_eval}[a.stage]()


if __name__ == "__main__":
    raise SystemExit(main())
