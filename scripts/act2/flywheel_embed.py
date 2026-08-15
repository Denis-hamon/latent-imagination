#!/usr/bin/env python3
"""Story 9.1 — embed + assemble pool v9 (promotion flywheel, node GPU).

v9 = v8 rows (UNTOUCHED, order preserved — append-only) + stage-2 flywheel
goal-free rows. Embedding recipe IDENTICAL to s14_pool (bit-identical S8/S14
lineage): s11.batched_embed (microsoft/unixcoder-base, CLS, max_length 512)
on the raw state/diff texts.

GOAL-FREE HONESTY: the flywheel pairs carry no gold diff, so E_goal is an
EXPLICIT zero vector and the json rows carry `goal_free: true`. The gold axis
(assess_patch / loao_energy) must skip goal_free rows — a fabricated goal
channel would invent evidence (R3). The goal-free axis served by risk_scan
uses only cd = E_state + E_diff and is unaffected.

Idempotent: same inputs regenerate the same bytes; aborts if v9 already
exists with different content.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
FLY = PILOT / "mcp-flywheel" / "flywheel-rows.json"
V8_JSON = PILOT / "latent-pool-v8.json"
V8_NPZ = PILOT / "latent-pool-v8.npz"
V9_JSON = PILOT / "latent-pool-v9.json"
V9_NPZ = PILOT / "latent-pool-v9.npz"

_spec = importlib.util.spec_from_file_location(
    "s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s11)


def sha(p: Path) -> str:
    return sha256(p.read_bytes()).hexdigest()


def main() -> int:
    if not FLY.is_file():
        print(f"ABSENT: {FLY} — run the flywheel stage 2 (assemble) first")
        return 2
    rows8 = json.loads(V8_JSON.read_text())
    d8 = np.load(V8_NPZ)
    fly = json.loads(FLY.read_text())
    if not fly:
        print("RIEN À PROMOUVOIR : flywheel-rows.json vide — pas de cérémonie.")
        return 0
    if not all(r.get("goal_free") for r in fly):
        print("ABORT: des lignes ne sont pas goal_free — la recette v9 exige "
              "l'homogénéité du lot (paires MCP sans gold).")
        return 2

    # idempotence : v9 déjà existant et identique -> no-op
    if V9_JSON.is_file() and V9_NPZ.is_file():
        rows9_old = json.loads(V9_JSON.read_text())
        if (len(rows9_old) == len(rows8) + len(fly)
                and rows9_old[:len(rows8)] == rows8
                and [r["task"] for r in rows9_old[len(rows8):]] == [r["task"] for r in fly]):
            print(f"DÉJÀ PROMU (no-op) : {V9_JSON.name} sha={sha(V9_JSON)[:16]}… "
                  f"{V9_NPZ.name} sha={sha(V9_NPZ)[:16]}…")
            return 0
        print("ABORT: v9 existe avec un contenu DIFFÉRENT — résolution manuelle "
              "(append-only : on n'écrase pas).")
        return 2

    import torch
    from transformers import AutoModel, AutoTokenizer

    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    model = AutoModel.from_pretrained("microsoft/unixcoder-base").eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    print(f"embed {len(fly)} lignes flywheel sur {device} "
          f"(préfixe v8 = {len(rows8)} lignes, intouché)", flush=True)

    E_s = s11.batched_embed(model, tok, [r["state"] for r in fly])
    E_d = s11.batched_embed(model, tok, [r["diff"] for r in fly])
    # goal_free : zéro EXPLICITE (pas un embed de chaîne vide, pas un gold inventé)
    E_g = np.zeros((len(fly), E_s.shape[1]), dtype=E_s.dtype)

    new_rows = []
    for r in fly:
        new_rows.append({
            "task": r["task"], "arm": r.get("arm", "flywheel"),
            "campaign": r.get("campaign", "mcp-flywheel-1"),
            "state": r["state"], "gold": "", "diff": r["diff"],
            "y": int(r["y"]),
            "goal_free": True,
            "provenance": r.get("provenance", {}),
        })
    rows9 = rows8 + new_rows
    cat = {k: np.concatenate([d8[k], v]) for k, v in
           (("E_state", E_s), ("E_diff", E_d), ("E_goal", E_g))}

    V9_JSON.write_text(json.dumps(rows9, ensure_ascii=False))
    np.savez_compressed(V9_NPZ, **cat)

    # vérifications d'intégrité
    assert len(rows9) == cat["E_state"].shape[0] == len(rows8) + len(fly)
    assert rows9[:len(rows8)] == rows8, "l'ordre append-only a bougé"
    print("OK v9 assemblé :")
    print(f"  {V9_JSON.name} : {len(rows9)} lignes ({len(rows8)} v8 + {len(fly)} flywheel) "
          f"sha={sha(V9_JSON)}")
    print(f"  {V9_NPZ.name}  : {cat['E_state'].shape} sha={sha(V9_NPZ)}")
    print(f"  positives v9 : {sum(r['y'] for r in rows9)} | goal_free : {len(fly)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
