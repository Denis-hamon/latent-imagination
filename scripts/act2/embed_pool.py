#!/usr/bin/env python3
"""Étape 1 du pont JEPA→code : embeddings denses pour le pool de patches Act II.

Pour chaque (task, arm, patch) :
- E_state : texte structuré = problem + F2P names + buggy source (tronc. 4 000 chars)
- E_diff : le diff généré
- E_goal : le gold.diff (= vrai fix dans ce corpus injecté)

Encodeur : microsoft/unixcoder-base (HF, ~1 GA de VRAM), du côté GPU du noeud.
Sortie : data/landing/act2-pilot/latent-pool.npz (+ métadonnées JSON par échantillon).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

BASE = Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot")


def batched_embed(model, tok, texts, bs=16):
    import torch
    out = []
    for i in range(0, len(texts), bs):
        tb = tok(texts[i:i + bs], padding=True, truncation=True, max_length=512,
                 return_tensors="pt")
        with torch.no_grad():
            v = model(**{k: t.to(model.device) for k, t in tb.items()}).last_hidden_state[:, 0]
        out.append(v.cpu().numpy())
    return np.concatenate(out)


def collect():
    """Walk results dirs of both campaigns (frozen32 = '', extension-128)."""
    rows = []
    for campaign in ("", "extension-128"):
        pdir = BASE / campaign / "results"
        if not pdir.is_dir():
            continue
        tasks = {t["instance_id"]: t for t in json.loads((BASE / campaign / "pilot-tasks.json").read_text())}
        for d in sorted(pdir.glob("*")):
            mf, pf, rf = d / "meta.json", d / "patch.diff", d / "run-result.json"
            if not (mf.is_file() and pf.is_file() and rf.is_file()):
                continue
            ptxt = pf.read_text()
            if not ptxt.strip():
                continue
            m = json.loads(mf.read_text()); r = json.loads(rf.read_text())
            if not r.get("patch_applied"):
                continue
            t = tasks[m["task"]]
            goldf = BASE / campaign / "control-gold" / m["task"].replace("/", "_") / "gold.diff"
            gold = goldf.read_text() if goldf.is_file() else ""
            rows.append({"task": m["task"], "arm": m["arm"], "campaign": campaign or "frozen32",
                         "state": (t["problem"][:1200] + "\n" + "; ".join(map(str, t["f2p"][:6]))),
                         "diff": ptxt, "gold": gold,
                         "y": 1 if r.get("f2p_pass") else 0})
    return rows


def main() -> int:
    import torch
    from transformers import AutoModel, AutoTokenizer

    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    model = AutoModel.from_pretrained("microsoft/unixcoder-base").to("cuda" if torch.cuda.is_available() else "cpu").eval()

    rows = collect()
    print(f"pool latent: {len(rows)} échantillons")
    states = [r["state"] for r in rows]
    diffs = [r["diff"] for r in rows]
    goals = [r["gold"] for r in rows]
    print("embed state…", flush=True); E_s = batched_embed(model, tok, states)
    print("embed diff…", flush=True); E_d = batched_embed(model, tok, diffs)
    print("embed gold…", flush=True); E_g = batched_embed(model, tok, goals)
    np.savez_compressed(BASE / "latent-pool.npz", E_state=E_s, E_diff=E_d, E_goal=E_g)
    (BASE / "latent-pool.json").write_text(json.dumps(rows, indent=1))
    print("OK:", BASE / "latent-pool.npz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
