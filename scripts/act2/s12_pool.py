#!/usr/bin/env python3
"""S12 — pool v7 : v6 + patchs générés (fenêtre s12-gen, auteur déclaré
MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-bf16).

Stages :
  --stage pool   : construction latent-pool-v7.json depuis les run-results de
                   s12_label_exec (chaîne : applied → py_compile → F2P → P2P ;
                   y=1 ssi f2p_pass ET (p2p_pass ou p2p non déclaré) ; dédup
                   sha256(diff) contre v6). state/gold repris des lignes v6 de
                   la même tâche (recette identique par construction).
  --stage embed  : embeddings uxc-base CLS-512 des NOUVELLES lignes seulement
                   (GPU node), recette bit-identique s11/embed_pool.
  --stage eval   : LOAO-strict, contrôle positif v6 GOLD (0.822/0.779 attendus),
                   v7 GOLD + GxF strict + courbe de sélectivité. Gate v2
                   pré-déclarée (AUC > 0.864 ET cov@≥0.95 > 30 %) : la décision
                   de promotion reste à la main de l'owner. CE SCRIPT NE PROMEUT
                   RIEN.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
RESULTS = PILOT / "s12-gen" / "results"
V7_JSON = PILOT / "latent-pool-v7.json"
V7_NPZ_NEW = PILOT / "s12-new-embed.npz"
V7_NPZ = PILOT / "latent-pool-v7.npz"
S12_MODEL = "MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-bf16"

_spec = importlib.util.spec_from_file_location(
    "s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s11)
norm, wilson, auc = s11.norm, s11.wilson, s11.auc
loao_energy, gxf_loao, report = s11.loao_energy, s11.gxf_loao, s11.report
COVERAGES, TARGET = s11.COVERAGES, s11.TARGET


def _v6():
    rows = json.loads((PILOT / "latent-pool-v6.json").read_text())
    du = np.load(PILOT / "latent-pool-v6.npz")
    return rows, du


def stage_pool() -> int:
    rows6, _ = _v6()
    bytask = {}
    for r in rows6:
        bytask.setdefault(r["task"], r)
    seen = {hashlib.sha256(r["diff"].strip().encode()).hexdigest()
            for r in rows6}
    new, skipped = [], []
    for rr in sorted(RESULTS.glob("*/run-result.json")):
        if rr.parent.name.startswith("smoke-"):
            continue
        res = json.loads(rr.read_text())
        mf = rr.parent / "meta.json"
        if not mf.is_file():
            skipped.append((res.get("task") or rr.parent.name, "gen-incomplet (meta manquante)"))
            continue
        _meta = json.loads(mf.read_text())  # parse preserved, value unused (frozen script)
        task = res["task"]
        if not res.get("patch_applied"):
            skipped.append((task, "non-applicable"))
            continue
        if res.get("py_compiles") is False:
            skipped.append((task, "ne-compile-pas"))
            continue
        f2p = bool(res.get("f2p_pass"))
        p2p_ok = res.get("p2p_pass", True)  # p2p non déclaré ⇒ pas de veto
        y = 1 if (f2p and p2p_ok) else 0
        ref = bytask.get(task)
        if ref is None:
            skipped.append((task, "tâche hors v6"))
            continue
        diff = (rr.parent / "patch.diff").read_text()
        h = hashlib.sha256(diff.strip().encode()).hexdigest()
        if h in seen:
            skipped.append((task, f"dédup {rr.parent.name}"))
            continue
        seen.add(h)
        new.append({
            "task": task, "arm": rr.parent.name.rsplit("-", 1)[-1],
            "campaign": "s12-gen", "author": S12_MODEL,
            "state": ref["state"], "diff": diff, "gold": ref["gold"], "y": y,
        })
    v7 = rows6 + new
    pos = sum(r["y"] for r in v7)
    out = {
        "n_v6": len(rows6), "n_new": len(new), "n_v7": len(v7),
        "positifs_v7": pos, "taches_v7": len({r["task"] for r in v7}),
        "new_positifs": sum(r["y"] for r in new),
        "skipped": len(skipped),
        "skipped_detail": skipped[:40],
    }
    V7_JSON.write_text(json.dumps(v7, indent=1))
    (PILOT / "s12-pool-build.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items()
                      if k != "skipped_detail"}, indent=1))
    print(f"OK {V7_JSON} ({len(v7)} lignes)")
    return 0


def stage_embed() -> int:
    import os
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    import torch
    from transformers import AutoModel, AutoTokenizer

    rows6, du6 = _v6()
    v7 = json.loads(V7_JSON.read_text())
    new = v7[len(rows6):]
    if not new:
        print("aucune nouvelle ligne à embarquer")
        return 0
    states = [r["state"] for r in new]
    diffs = [r["diff"] for r in new]
    goals = [r["gold"] for r in new]
    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    device = ("cuda" if torch.cuda.is_available() else "cpu")
    model = (AutoModel.from_pretrained("microsoft/unixcoder-base")
             .to(device).eval())
    print(f"embed {len(new)} nouvelles lignes sur {device}", flush=True)
    E_s = s11.batched_embed(model, tok, states)
    E_d = s11.batched_embed(model, tok, diffs)
    E_g = s11.batched_embed(model, tok, goals)
    np.savez_compressed(V7_NPZ_NEW, E_state=E_s, E_diff=E_d, E_goal=E_g)
    # concat immédiat v6 + new
    np.savez_compressed(V7_NPZ,
                        **{k: np.concatenate([du6[k], d])
                           for k, d in (("E_state", E_s), ("E_diff", E_d),
                                         ("E_goal", E_g))})
    print(f"OK {V7_NPZ} ({len(v7)} lignes)")
    return 0


def stage_eval() -> int:
    rows6, du6 = _v6()
    v7 = json.loads(V7_JSON.read_text())
    dv7 = np.load(V7_NPZ)
    y6 = np.array([int(r["y"]) for r in rows6])
    t6 = np.array([r["task"] for r in rows6])
    maj6 = max(y6.mean(), 1 - y6.mean())
    EU6 = {k: norm(du6[k]) for k in ("E_state", "E_diff", "E_goal")}
    cd6 = norm(EU6["E_state"] + EU6["E_diff"])
    cg6 = norm(EU6["E_state"] + EU6["E_goal"])
    pred, conf, sco = loao_energy(cd6, cg6, y6, t6)
    ctrl = report("CTRL v6 GOLD (=S7/S10/S11)", pred, conf, sco, y6, maj6)
    ok = abs(ctrl["auc"] - 0.822) < 0.01 and abs(ctrl["acc100"] - 0.779) < 0.005
    print(f"  → contrôle {'OK' if ok else 'DÉRIVE — STOP'}")
    if not ok:
        return 1
    y7 = np.array([int(r["y"]) for r in v7])
    t7 = np.array([r["task"] for r in v7])
    maj7 = max(y7.mean(), 1 - y7.mean())
    camp = np.array(["v6"] * len(rows6) + ["s12"] * (len(v7) - len(rows6)))
    EU7 = {k: norm(dv7[k]) for k in ("E_state", "E_diff", "E_goal")}
    cd7 = norm(EU7["E_state"] + EU7["E_diff"])
    cg7 = norm(EU7["E_state"] + EU7["E_goal"])
    out = {"n_v7": len(v7), "positifs_v7": int(y7.sum()),
           "majority_v7": float(maj7),
           "n_tasks_v7": len(set(t7)),
           "positive_control_v6": {"expected": [0.822, 0.779],
                                   "got": [ctrl["auc"], ctrl["acc100"]],
                                   "ok": bool(ok)},
           "variants": {}}
    pred, conf, sco = loao_energy(cd7, cg7, y7, t7)
    out["variants"]["v7_gold"] = report("V7 GOLD uxc", pred, conf, sco, y7, maj7)
    pred, conf, sco = gxf_loao(cd7, cg7, y7, t7)
    out["variants"]["v7_gxf_strict"] = report("V7 GxF strict", pred, conf, sco,
                                              y7, maj7)
    # queue haute-confiance : qui l'habite (v6 vs s12) ?
    order = np.argsort(-conf)
    m = max(1, round(len(y7) * 0.25))
    top = order[:m]
    out["queue_top25"] = {
        c: {"n": int((camp[top] == c).sum()),
            "acc": float((pred[top][camp[top] == c]
                          == y7[top][camp[top] == c]).mean())
            if (camp[top] == c).any() else None}
        for c in ("v6", "s12")}
    # gate v2 pré-déclarée le 2026-08-10 (inchangée)
    gate_pass = (out["variants"]["v7_gold"]["auc"] > 0.864
                 and out["variants"]["v7_gold"]["max_cov"] > 0.30)
    gate_pass_x = (out["variants"]["v7_gxf_strict"]["auc"] > 0.864
                   and out["variants"]["v7_gxf_strict"]["max_cov"] > 0.30)
    out["gate_v2"] = {"rule": "AUC>0.864 ET cov@≥0.95>30 % (pré-déclarée)",
                      "gold_pass": bool(gate_pass),
                      "gxf_pass": bool(gate_pass_x),
                      "rappel": "aucune promotion automatique — owner décide"}
    (PILOT / "s12-pool-v7-eval.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)[:2000])
    print(f"\nArtefact : {PILOT / 's12-pool-v7-eval.json'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["pool", "embed", "eval"], required=True)
    a = ap.parse_args()
    return {"pool": stage_pool, "embed": stage_embed, "eval": stage_eval}[a.stage]()


if __name__ == "__main__":
    raise SystemExit(main())
