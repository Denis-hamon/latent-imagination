#!/usr/bin/env python3
"""Story 10.3 — embed + assemble pool v10 = v9 (UNTOUCHED, append-only) +
delta flywheel goal-free (lignes NON encore promues). Généralisation de
flywheel_embed.py (9.1, bit-identical recipe s14/S8 lineage via s11.batched_embed).

GOAL-FREE HONESTY (inchangée) : E_goal = zéro EXPLICITE, `goal_free: true`
dans la ligne JSON ; l'axe gold (assess_patch / loao_energy) doit sauter ces
lignes — jamais d'évidence inventée (R3).

Idempotent : mêmes entrées → mêmes octets ; ABORT si v10 existe avec un
contenu DIFFÉRENT (append-only : on n'écrase jamais).

Tourne sur le node (GPU, torch + transformers dans le .venv node).
Run (node): .venv/bin/python scripts/act2/promote_v10_embed.py
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
SRC_JSON = PILOT / "latent-pool-v9.json"
SRC_NPZ = PILOT / "latent-pool-v9.npz"
DST_JSON = PILOT / "latent-pool-v10.json"
DST_NPZ = PILOT / "latent-pool-v10.npz"

_spec = importlib.util.spec_from_file_location(
    "s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s11)


def sha(p: Path) -> str:
    return sha256(p.read_bytes()).hexdigest()


def main() -> int:
    if not FLY.is_file():
        print(f"ABSENT: {FLY}")
        return 2
    rows_src = json.loads(SRC_JSON.read_text())
    d_src = np.load(SRC_NPZ)
    fly = json.loads(FLY.read_text())
    existing = {r["task"] for r in rows_src}
    delta = [r for r in fly if r["task"] not in existing]
    if not delta:
        print("RIEN DE NOUVEAU : toutes les lignes flywheel sont déjà dans v9.")
        return 0
    if not all(r.get("goal_free") for r in delta):
        print("ABORT: lignes non goal_free dans le delta — homogénéité exigée.")
        return 2
    if DST_JSON.is_file() and DST_NPZ.is_file():
        rows_old = json.loads(DST_JSON.read_text())
        expect = len(rows_src) + len(delta)
        if (len(rows_old) == expect and rows_old[:len(rows_src)] == rows_src
                and [r["task"] for r in rows_old[len(rows_src):]] == [r["task"] for r in delta]):
            print(f"DÉJÀ PROMU (no-op) : {DST_JSON.name} sha={sha(DST_JSON)[:16]}…")
            return 0
        print("ABORT: v10 existe avec un contenu DIFFÉRENT — résolution manuelle.")
        return 2

    import torch
    from transformers import AutoModel, AutoTokenizer

    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    model = AutoModel.from_pretrained("microsoft/unixcoder-base").eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    print(f"embed {len(delta)} lignes flywheel (delta hors v9) sur {device} ; "
          f"préfixe v9 = {len(rows_src)} lignes, intouché", flush=True)
    E_s = s11.batched_embed(model, tok, [r["state"] for r in delta])
    E_d = s11.batched_embed(model, tok, [r["diff"] for r in delta])
    E_g = np.zeros((len(delta), E_s.shape[1]), dtype=E_s.dtype)

    new_rows = []
    for r in delta:
        new_rows.append({
            "task": r["task"], "arm": r.get("arm", "flywheel"),
            "campaign": r.get("campaign", "mcp-flywheel-1"),
            "state": r["state"], "gold": "", "diff": r["diff"],
            "y": int(r["y"]), "goal_free": True,
            "provenance": r.get("provenance", {}),
        })
    rows10 = rows_src + new_rows
    cat = {k: np.concatenate([d_src[k], v]) for k, v in
           (("E_state", E_s), ("E_diff", E_d), ("E_goal", E_g))}
    DST_JSON.write_text(json.dumps(rows10, ensure_ascii=False))
    np.savez_compressed(DST_NPZ, **cat)
    assert len(rows10) == cat["E_state"].shape[0] == len(rows_src) + len(delta)
    assert rows10[:len(rows_src)] == rows_src, "l'ordre append-only a bougé"
    pos10 = sum(r["y"] for r in rows10)
    fams = {r["task"].split(".")[0] for r in rows10}
    print("OK v10 assemblé :")
    print(f"  {DST_JSON.name}: {len(rows10)} lignes ({len(rows_src)} v9 + {len(delta)} flywheel-delta) "
          f"sha={sha(DST_JSON)[:16]}…")
    print(f"  {DST_NPZ.name}: {cat['E_state'].shape} sha={sha(DST_NPZ)[:16]}…")
    print(f"  positifs: {pos10}/{len(rows10)} ({pos10/len(rows10):.1%}) · familles: {len(fams)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
