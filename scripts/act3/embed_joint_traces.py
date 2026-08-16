#!/usr/bin/env python3
"""Story 13.4 — embed des traces tests + composition jointe (node, unixcoder).

E_joint = norm([cd ; ctrace]) avec cd = norm(norm(E_state)+norm(E_diff)) du pool
v10. Trace ABSENTE ⇒ vecteur nul EXPLICITE + masque has_trace (jamais de trace
inventée — FR-3, disclosed dans l'artefact candidat).
Run (node): .venv/bin/python scripts/act3/embed_joint_traces.py
"""
from __future__ import annotations

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
    rows = json.loads((PILOT / "latent-pool-v10.json").read_text())
    d = np.load(PILOT / "latent-pool-v10.npz")
    traces = []
    with (PILOT / "latent-pool-v10-traces.jsonl").open() as fh:
        for l in fh:
            traces.append(json.loads(l))
    assert [t["task"] for t in traces] == [r["task"] for r in rows], \
        "ordre traces != ordre pool — refus de joindre (pas de devinette)"
    texts = [t["trace"] for t in traces]
    has_trace = np.array([bool(t.strip()) for t in texts])

    import torch
    from transformers import AutoModel, AutoTokenizer

    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    model = AutoModel.from_pretrained("microsoft/unixcoder-base").eval().to(
        "cuda" if torch.cuda.is_available() else "cpu")
    print(f"embed {int(has_trace.sum())} traces réelles (unixcoder)", flush=True)
    E_t = np.zeros((len(texts), 768), dtype=np.float32)
    idx = np.where(has_trace)[0].tolist()
    if idx:
        E_t[idx] = s11.batched_embed(model, tok, [texts[i] for i in idx])
    Es, Ed = s11.norm(d["E_state"]), s11.norm(d["E_diff"])
    cd = s11.norm(Es + Ed)
    ct = s11.norm(E_t) if idx else E_t
    E_joint = np.concatenate([cd, ct], axis=1)
    E_joint = E_joint / (np.linalg.norm(E_joint, axis=1, keepdims=True) + 1e-9)
    out = PILOT / "latent-pool-v10-joint.npz"
    np.savez_compressed(out, E_joint=E_joint, has_trace=has_trace.astype(np.int8))
    print(f"OK: {out.name} E_joint {E_joint.shape} | traces {int(has_trace.sum())}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
