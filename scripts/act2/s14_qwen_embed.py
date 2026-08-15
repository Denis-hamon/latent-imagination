#!/usr/bin/env python3
"""S14 (node) — embeddings Qwen2.5-Coder-7B-Instruct last-token pour les pools
étendus (v8+), recette bit-identique à S8 (fp16, 512 tokens, sdpa, last non-pad).

Incrémental : si l'npz cible existe avec k lignes préfixes stables (l'ordre des
pools est append-only par construction de s14_pool), seules les lignes [k:N]
sont embarquées. Préfixe initial = latent-pool-Qwen2.5-Coder-7B-Instruct-last.npz
(les 145 lignes v6, alignées par construction v8⊇v7⊇v6).

Usage : .venv/bin/python s14_qwen_embed.py <pool.json> <out.npz>
0 call galere — GPU node uniquement.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

BASE = Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot")
MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
SEED_NPZ = BASE / "latent-pool-Qwen2.5-Coder-7B-Instruct-last.npz"


def batched_embed(model, tok, texts, device, bs=4):
    import torch
    out = []
    for i in range(0, len(texts), bs):
        tb = tok(texts[i:i + bs], padding=True, truncation=True,
                 max_length=512, return_tensors="pt")
        tb = {k: t.to(device) for k, t in tb.items()}
        with torch.no_grad():
            hs = model(**tb).last_hidden_state
        idx = tb["attention_mask"].sum(1) - 1
        last = hs[torch.arange(hs.shape[0]), idx]
        out.append(last.float().cpu().numpy())
    return np.concatenate(out)


def main() -> int:
    pool_f = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "latent-pool-v8.json"
    out_f = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "latent-pool-v8-qwen7b-last.npz"
    rows = json.loads(pool_f.read_text())
    have = {"E_state": None, "E_diff": None, "E_goal": None}
    k = 0
    if out_f.is_file():
        ex = np.load(out_f)
        k = ex["E_state"].shape[0]
        have = {x: ex[x] for x in have}
        if k > len(rows):
            print(f"ERREUR : npz {k} lignes > pool {len(rows)}")
            return 1
    elif SEED_NPZ.is_file() and len(rows) >= 145:
        seed = np.load(SEED_NPZ)
        have = {x: seed[x] for x in have}
        k = seed["E_state"].shape[0]
        print(f"seed v6 Qwen : {k} lignes")
    if k >= len(rows):
        print(f"déjà complet ({k} lignes)")
        return 0

    import torch
    from transformers import AutoModel, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    t0 = time.time()
    model = AutoModel.from_pretrained(MODEL, dtype=torch.float16,
                                      device_map="auto",
                                      attn_implementation="sdpa").eval()
    device = next(model.parameters()).device
    print(f"modèle chargé en {time.time()-t0:.0f}s sur {device}", flush=True)

    new = rows[k:]
    acc = {}
    for kind, f in (("E_state", "state"), ("E_diff", "diff"), ("E_goal", "gold")):
        t0 = time.time()
        acc[kind] = batched_embed(model, tok, [r[f] for r in new], device)
        print(f"  {kind}: {acc[kind].shape} en {time.time()-t0:.0f}s", flush=True)
    np.savez_compressed(out_f,
                        **{x: np.concatenate([have[x], acc[x]]) for x in have})
    print(f"OK {out_f} ({k + len(new)} lignes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
