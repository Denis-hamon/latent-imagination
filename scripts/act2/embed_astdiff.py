#!/usr/bin/env python3
"""Story 13.2 — re-embed des diffs NORMALISÉS AST (node, unixcoder-base).

Produit latent-pool-<v>-astdiff.npz : E_state et E_goal IDENTIQUES au pool
source (copie bit-à-bit), SEUL E_diff est re-calculé sur le texte normalisé.
Isoler la variable (texture du diff) sans toucher au reste de l'instrument.
Run (node): .venv/bin/python scripts/act2/embed_astdiff.py --pool v10
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="v10")
    args = ap.parse_args()
    src_npz = PILOT / f"latent-pool-{args.pool}.npz"
    src_json = PILOT / f"latent-pool-{args.pool}.json"
    norm_f = PILOT / f"latent-pool-{args.pool}-astdiff-diffs.jsonl"
    rows = json.loads(src_json.read_text())
    norms = {}
    with norm_f.open() as fh:
        for l in fh:
            d = json.loads(l)
            norms[d["task"]] = d["norm_diff"]
    missing = [r["task"] for r in rows if r["task"] not in norms]
    if missing:
        print(f"ABORT: {len(missing)} diffs normalisés manquants — pas d'invention")
        return 2

    import torch
    from transformers import AutoModel, AutoTokenizer

    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    model = AutoModel.from_pretrained("microsoft/unixcoder-base").eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    texts = [norms[r["task"]] for r in rows]
    print(f"embed {len(texts)} diffs normalisés sur {device}", flush=True)
    E_d = s11.batched_embed(model, tok, texts)
    d0 = np.load(src_npz)
    out = PILOT / f"latent-pool-{args.pool}-astdiff.npz"
    # E_state / E_goal : copie bit-à-bit du pool source (variable isolée = E_diff)
    assert d0["E_state"].shape == E_d.shape and d0["E_goal"].shape == E_d.shape
    np.savez_compressed(out, E_state=d0["E_state"], E_diff=E_d, E_goal=d0["E_goal"])
    print(f"OK: {out.name} ({E_d.shape})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
