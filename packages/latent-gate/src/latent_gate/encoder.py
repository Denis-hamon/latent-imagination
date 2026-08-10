"""Encodeur gelé uniXCoder-base (CLS, 512 tokens) — la recette mesurée S4.

Contrôle positif de campagne : sur latent-pool, cette extraction bit-reproduit
AUC 0.817 / acc LOAO 0.735 / S1 1.000@25 % (run local MPS == run node GPU).
Ne rien changer ici sans relancer ce contrôle (scripts/act2/s4_encoder_swap.py).
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

MODEL_ID = os.environ.get("LI_ENCODER", "microsoft/unixcoder-base")
MAX_LEN = 512


@lru_cache(maxsize=1)
def _load():
    os.environ.setdefault("HF_HUB_OFFLINE", "0")  # le service DOIT pouvoir tirer
    import torch
    from transformers import AutoModel, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    device = "mps" if torch.backends.mps.is_available() else (
        "cuda" if torch.cuda.is_available() else "cpu")
    model = AutoModel.from_pretrained(MODEL_ID).to(device).eval()
    return tok, model, device


def embed_one(text: str) -> np.ndarray:
    """Embedding CLS L2-brut (la normalisation intervient dans scoring)."""
    import torch
    tok, model, device = _load()
    tb = tok([text], padding=True, truncation=True, max_length=MAX_LEN,
             return_tensors="pt")
    with torch.no_grad():
        h = model(**{k: t.to(device) for k, t in tb.items()}).last_hidden_state
    return h[0, 0].float().cpu().numpy()


def embed_batch(texts: list[str], bs: int = 16) -> np.ndarray:
    import torch
    tok, model, device = _load()
    out = []
    for i in range(0, len(texts), bs):
        tb = tok(texts[i:i + bs], padding=True, truncation=True,
                 max_length=MAX_LEN, return_tensors="pt")
        with torch.no_grad():
            h = model(**{k: t.to(device) for k, t in tb.items()}).last_hidden_state
        out.append(h[:, 0].float().cpu().numpy())
    return np.concatenate(out)
