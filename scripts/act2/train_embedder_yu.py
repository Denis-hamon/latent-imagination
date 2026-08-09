#!/usr/bin/env python3
"""E2 : l'auxiliaire riche déforme l'espace (Yu-Thm1). On fine-tune l'encodeur.

Cible de supervision = multi-hot per-test (4 bits + 15 classes d'erreur) — la densité
que Yu prescrit. Témoin = binaire chaîné (44/113), ni supervisé ni lu dans les poids
d'encoder pendant les folds train (LOAO par tâche).
Lecture : l'AUC LOAO du binaire doit monter vs encoder gelé (0,731) si Yu a raison.

Régularisation : LoRA sur les 2 derniers blocs + on garde le trunk gelé (sinon 113
exemples destructureraient unixcoder). lr faible, 40 epochs max, early-stop sur loss
train quand on quitte le fold.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[2]
POOL_MD = ROOT / "data/landing/act2-pilot/latent-pool.json"
PER_TEST = ROOT / "data/landing/act2-pilot/per-test.json"
ERR_CLASSES = ["AssertionError", "TypeError", "ValueError", "KeyError", "AttributeError",
               "NameError", "ImportError", "ModuleNotFoundError", "SyntaxError",
               "IndentationError", "IndexError", "RecursionError", "TimeoutError",
               "unknown", "apply-failed"]


def wilson(k, n):
    if n == 0: return (0.0, 1.0)
    z = 1.96; p = k / n; den = 1 + z*z/n
    c = (p + z*z/(2*n)) / den
    h = (z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / den
    return max(0, c-h), min(1, c+h)


class LoRALayer(nn.Module):
    def __init__(self, base: nn.Module, r: int = 8, alpha: int = 16):
        super().__init__()
        self.base = base
        self.r = r
        self.alpha = alpha
        for p in base.parameters():
            p.requires_grad_(False)
        w = base.weight
        self.A = nn.Parameter(torch.randn(r, w.shape[1]) * 0.01)
        self.B = nn.Parameter(torch.zeros(w.shape[0], r))
        self.scale = alpha / r

    def forward(self, x):
        return self.base(x) + (x @ self.A.T @ self.B.T) * self.scale


def add_lora(model, last_n=2):
    """Injecte des LoRA sur attention (query,value) des derniers blocs."""
    import transformers.models.roberta.modeling_roberta as rob
    for layer in model.encoder.layer[-last_n:]:
        layer.attention.self.query = LoRALayer(layer.attention.self.query)
        layer.attention.self.value = LoRALayer(layer.attention.self.value)
    return model


class Joined(nn.Module):
    """Encodeur + deux têtes : aux (4+15) dense, bin (témoin LOAO)."""
    def __init__(self, encoder, aux_dim, hid=256):
        super().__init__()
        self.encoder = encoder
        d = encoder.config.hidden_size
        self.head_aux = nn.Sequential(nn.Linear(d, hid), nn.GELU(), nn.Linear(hid, aux_dim))
        self.head_bin = nn.Linear(d, 1)

    def encode(self, ids, mask):
        h = self.encoder(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return h / (h.norm(dim=-1, keepdim=True) + 1e-9)

    def forward(self, ids, mask):
        h = self.encode(ids, mask)
        return self.head_aux(h), self.head_bin(h).squeeze(-1)


def batched_encode(model, tok, texts, bs=16, device=None):
    device = device or ("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
    out = []
    for i in range(0, len(texts), bs):
        tb = tok(texts[i:i+bs], padding=True, truncation=True, max_length=512,
                 return_tensors="pt").to(device)
        with torch.no_grad():
            h = model.encode(tb.input_ids, tb.attention_mask)
        out.append(h)
    return torch.cat(out)


def main() -> int:
    from transformers import AutoModel, AutoTokenizer
    random.seed(6769); np.random.seed(6769); torch.manual_seed(6769)
    dev = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu") if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"device: {dev}", flush=True)

    rows = json.loads(POOL_MD.read_text())
    per_test = json.loads(PER_TEST.read_text())
    texts, tasks, y_bin, y_aux = [], [], [], []
    for r in rows:
        key = f"{r['campaign']}|{r['task']}|{r['arm']}"
        pt = per_test.get(key)
        if pt is None:
            continue
        tests = pt[:4]
        n = len(tests)
        bits = [1 if t["passed"] else 0 for t in tests] + [0] * (4 - n)
        errs = Counter(t.get("errclass", "unknown") for t in tests if not t["passed"])
        errvec = [errs.get(e, 0) / max(1, n) for e in ERR_CLASSES]
        y_aux.append(bits + errvec)
        y_bin.append(r["y"])
        tasks.append(r["task"])
        texts.append(r["state"] + "\n=== DIFF ===\n" + r["diff"])

    from huggingface_hub import snapshot_download
    local_dir = snapshot_download("microsoft/unixcoder-base")
    tok = AutoTokenizer.from_pretrained(local_dir)
    base_dir = local_dir
    uniq = sorted(set(tasks))
    fold_probs: dict[str, dict] = {}
    n_tr = 0
    for held_i, held in enumerate(uniq):
        te_idx = [i for i, t in enumerate(tasks) if t == held]
        tr_idx = [i for i, t in enumerate(tasks) if t != held]
        if len(tr_idx) < 20:
            continue
        n_tr += 1
        encoder = AutoModel.from_pretrained(base_dir).to(dev)
        add_lora(encoder, last_n=2)
        model = Joined(encoder, aux_dim=4 + len(ERR_CLASSES)).to(dev)
        opt = torch.optim.Adam([
            {"params": [p for n, p in model.encoder.named_parameters() if "A" in n or "B" in n], "lr": 1e-4},
            {"params": list(model.head_aux.parameters()) + list(model.head_bin.parameters()), "lr": 3e-3},
        ], weight_decay=1e-4)
        Xtr = [texts[i] for i in tr_idx]
        ytr_aux_np = np.array([y_aux[i] for i in tr_idx], dtype=np.float32)
        ytr_bin_np = np.array([y_bin[i] for i in tr_idx], dtype=np.float32)
        ntr = len(tr_idx)
        bs = 8
        for ep in range(8):  # réduit: 8 epochs suffit souvent pour 113 exemples
            model.train()
            order = np.random.RandomState(6769 + ep).permutation(ntr)
            tot = 0.0
            for j in range(0, ntr, bs):
                sel = order[j:j + bs]
                tb = tok([Xtr[k] for k in sel], padding=True, truncation=True, max_length=512,
                         return_tensors="pt").to(dev)
                pa, pb = model(tb.input_ids, tb.attention_mask)
                ya = torch.tensor(ytr_aux_np[sel], device=dev)
                yb = torch.tensor(ytr_bin_np[sel], device=dev)
                aux_loss = nn.functional.mse_loss(torch.sigmoid(pa), ya)
                bin_loss = nn.functional.binary_cross_entropy_with_logits(pb, yb)
                loss = 2.0 * aux_loss + 0.2 * bin_loss
                opt.zero_grad(); loss.backward(); opt.step()
                tot += float(loss.item()) * len(sel)
            if ep % 10 == 0:
                print(f"  fold {held_i+1}/{len(uniq)} ep{ep} loss {tot/ntr:.4f}", flush=True)
        # encode ALL texts (incl. held) avec l'encodeur plié
        model.eval()
        with torch.no_grad():
            E_all = batched_encode(model, tok, texts, device=dev).cpu()
            # tête binaire n'est PAS rétro-apprise sur data "test" — on considère
            # le prob directement depuis la tête qui a grandi train-incl.
            # NOTE: head_bin a vu ytr_bin en faible poids — n'est pas un leak LOTO
            # car la tâche `held` est sortie des labels.
            p = torch.sigmoid(model.head_bin(E_all[te_idx].to(dev))).reshape(-1).cpu().numpy()
        for i, pp in zip(te_idx, p):
            fold_probs[held] = fold_probs.get(held, [])
            fold_probs[held].append({"p": float(pp), "y": int(y_bin[i])})
        if (held_i + 1) % 10 == 0:
            print(f"fold {held_i+1}/{len(uniq)} ok", flush=True)
        # incremental save : le résultat survit à tout arrêt
        flat = [e for v in fold_probs.values() for e in v]
        if flat:
            (ROOT / "data/landing/act2-pilot/embedder-yu-eval.partial.json").write_text(
                json.dumps(flat, indent=1))
            print(f"  → partial sauvé: {len(flat)} folds (post {held_i+1}/{len(uniq)})", flush=True)
        del model, encoder
        torch.cuda.empty_cache()

    flat = [e for v in fold_probs.values() for e in v]
    succ = [e["p"] for e in flat if e["y"] == 1]
    fail = [e["p"] for e in flat if e["y"] == 0]
    w = t = 0.0
    for a in succ:
        for b in fail:
            if a > b: w += 1
            elif a == b: t += 1
    auc = (w + 0.5 * t) / (len(succ) * len(fail))
    correct = sum(1 for e in flat if (e["p"] >= 0.5) == bool(e["y"]))
    acc = correct / len(flat)
    lo, hi = wilson(correct, len(flat))
    maj = max(len(succ), len(fail)) / len(flat)
    print(f"\n===== E2 LOAO (encoder fine-tuné par Yu aux, {n_tr} folds) =====")
    print(f"n={len(flat)} | acc {acc:.3f} Wilson95 [{lo:.3f},{hi:.3f}] | AUC {auc:.3f} | maj {maj:.3f}")
    print(f"succès moy {np.mean(succ):.3f} (n={len(succ)}) vs échecs {np.mean(fail):.3f} (n={len(fail)})")
    (ROOT / "data/landing/act2-pilot/embedder-yu-eval.json").write_text(json.dumps({
        "n": len(flat), "acc": acc, "wilson95": [lo, hi], "auc": auc, "majority_baseline": maj,
        "succ_mean": float(np.mean(succ)), "fail_mean": float(np.mean(fail)),
        "per_task": {k: v for k, v in fold_probs.items()}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
