#!/usr/bin/env python3
"""S8 — CWM (Meta FAIR, 32B) comme encodeur gelé : le mid-training sur la
DYNAMIQUE porte-t-il mieux le signal que les encodeurs statiques ?

Contexte : S4 a montré uxc-base > jina/codet5p/codebert à échelle ~110-160M —
tous des encodeurs de code STATIQUE. CWM est qualitativement différent : mid-
entraîné sur trajectoires observation-action (traces d'exécution Python +
ForagerAgent mutate/fix docker). Notre tâche (état, diff) → F2P est exactement
leur paradigme mutate-fix. Test : hidden states de facebook/cwm-pretrain
(checkpoint post-mid-train, "dynamique pure", avant SFT/RL) sur le pool v6.

Protocole strictement identique à S4 pour comparabilité : mêmes 145×3 textes
(state/diff/gold de latent-pool-v6.json), troncature 512 tokens, aucun
entraînement. Deux poolings (decoder-only : pas de CLS) :
  - last  : hidden state du dernier token non-paddé (usage LLM2Vec)
  - mean  : moyenne masquée par l'attention
Sorties node : data/landing/act2-pilot/latent-pool-cwm-{last,mean}.npz
L'évaluation (AUC GOLD / acc LOAO / cov@≥0.95) est faite Mac-side avec le
même code que S4/S7.

Contamination déclarée : repos swe-smith possibles dans les 3.15k repos
ForagerAgent (décontamination SWE-bench seulement, pas SWE-smith) ; les labels
(mutants synthétiques récents) sont non-publiés — pas de mémorisation du
verdict possible ; le code statique des repos était déjà dans tout pretraining.
Run : node WMEL-gpu-strong, 2× L40S, device_map auto, bf16. 0 call galere.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

BASE = Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot")
MODEL = sys.argv[1] if len(sys.argv) > 1 else "facebook/cwm-pretrain"
SLUG = MODEL.split("/")[-1].replace("cwm-", "cwm-")


def batched_embed(model, tok, texts, device, bs=4):
    import torch
    embs_last, embs_mean = [], []
    for i in range(0, len(texts), bs):
        tb = tok(texts[i:i + bs], padding=True, truncation=True,
                 max_length=512, return_tensors="pt")
        tb = {k: t.to(device) for k, t in tb.items()}
        with torch.no_grad():
            hs = model(**tb).last_hidden_state  # (B, T, H)
        mask = tb["attention_mask"]
        # last non-padded token
        idx = mask.sum(1) - 1  # (B,)
        last = hs[torch.arange(hs.shape[0]), idx]
        mean = (hs * mask.unsqueeze(-1)).sum(1) / mask.sum(1).clamp(min=1).unsqueeze(-1)
        embs_last.append(last.float().cpu().numpy())
        embs_mean.append(mean.float().cpu().numpy())
    return np.concatenate(embs_last), np.concatenate(embs_mean)


def main() -> int:
    import torch
    from transformers import AutoModel, AutoTokenizer

    rows = json.loads((BASE / "latent-pool-v6.json").read_text())
    texts = {"E_state": [r["state"] for r in rows],
             "E_diff": [r["diff"] for r in rows],
             "E_goal": [r["gold"] for r in rows]}
    print(f"pool v6 : {len(rows)} échantillons × 3 textes — modèle {MODEL}")

    tok = AutoTokenizer.from_pretrained(MODEL)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    t0 = time.time()
    model = AutoModel.from_pretrained(
        MODEL, dtype=torch.float16, device_map="auto",
        attn_implementation="sdpa").eval()
    device = next(model.parameters()).device
    print(f"modèle chargé en {time.time()-t0:.0f}s, device_map sur "
          f"{torch.cuda.device_count()} GPU")

    acc_last, acc_mean = {}, {}
    for kind, tks in texts.items():
        t0 = time.time()
        last, mean = batched_embed(model, tok, tks, device)
        acc_last[kind.split("_")[1] if "_" in kind else kind] = last
        acc_mean[kind.split("_")[1] if "_" in kind else kind] = mean
        print(f"  {kind}: {last.shape} en {time.time()-t0:.0f}s", flush=True)

    np.savez_compressed(BASE / f"latent-pool-{SLUG}-last.npz",
                        E_state=acc_last["state"], E_diff=acc_last["diff"],
                        E_goal=acc_last["goal"])
    np.savez_compressed(BASE / f"latent-pool-{SLUG}-mean.npz",
                        E_state=acc_mean["state"], E_diff=acc_mean["diff"],
                        E_goal=acc_mean["goal"])
    print(f"OK: latent-pool-{SLUG}-last.npz / -mean.npz sous {BASE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
