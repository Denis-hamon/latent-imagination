#!/usr/bin/env python3
"""Fine-équipe énergie multi-tâches, LOAO-strict.

Architecture (tout gelé sauf la tête) :
  x = [E_state, E_diff] (unixcoder, frozen)  → MLP(1536→256) → 3 têtes :
    1) binary F2P-pass (4 tests chaînés, protocole d'origine)   — superviseur principal
    2) multi-hot Yu-aux : 4 bits pass-per-test + 15 classes d'erreur (densité=19)
    3) consistance bisimulation : ||emb(diff)−emb(mutat(diff))||² sur 3 mutants/token-rename

Gradient sur la tête seule. 69 folds LOAO (une tâche entière tenue dehors à chaque tour).
Le code apprend sur les AUTRES tâches, évalue sur la tâche cachée : aucune fuite.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch import nn

ROOT = Path("/home/ubuntu/latent-imagination")

POOL_MD = ROOT / "data/landing/act2-pilot/latent-pool.json"
PER_TEST = ROOT / "data/landing/act2-pilot/per-test.json"

ERR_CLASSES = ["AssertionError", "TypeError", "ValueError", "KeyError", "AttributeError",
               "NameError", "ImportError", "ModuleNotFoundError", "SyntaxError",
               "IndentationError", "IndexError", "RecursionError", "TimeoutError",
               "unknown", "apply-failed"]
N_ERR = len(ERR_CLASSES)

IDENT = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")


def mutate_diff(text: str, mapping: dict[str, str]) -> str:
    """Renomme uniquement les noms présents dans le diff (hors mots-clés)."""
    KEYS = {"diff", "index", "from", "import", "def", "class", "return", "if", "else",
            "not", "None", "True", "False", "self", "for", "in", "and", "or", "is",
            "raise", "pass", "with", "as", "try", "except", "git", "new", "file", "mode"}
    def _rep(m):
        tok = m.group(0)
        if tok in KEYS or tok[:2] == "a/" or tok[:2] == "b/":
            return tok
        return mapping.get(tok, tok)
    return IDENT.sub(_rep, text)


def make_mutants(patch: str, k: int = 3, seed: int = 7) -> list[str]:
    toks = sorted({t for t in IDENT.findall(patch)
                   if len(t) > 2 and t[0].islower() and t not in
                   {"diff","index","from","import","def","class","return","if","else","not",
                    "None","True","False","self","for","in","and","or","is","raise","pass",
                    "with","as","try","except","git","new","file","mode"}})[:40]
    outs = []
    for i in range(k):
        perm = [f"mut{i}_{t}" for t in toks]
        mapping = dict(zip(toks, perm))
        outs.append(mutate_diff(patch, mapping))
    return outs


def batched_embed(texts, model, tok, bs=16):
    dev = next(model.parameters()).device
    out = []
    for i in range(0, len(texts), bs):
        tb = tok(texts[i:i + bs], padding=True, truncation=True, max_length=512,
                 return_tensors="pt").to(dev)
        with torch.no_grad():
            v = model(**tb).last_hidden_state[:, 0]
        out.append(v)
    return torch.cat(out)


class Head(nn.Module):
    def __init__(self, dim=1536, hid=256):
        super().__init__()
        self.trunk = nn.Sequential(nn.Linear(dim, hid), nn.GELU(), nn.LayerNorm(hid),
                                   nn.Linear(hid, hid), nn.GELU())
        self.bin = nn.Linear(hid, 1)
        self.aux = nn.Linear(hid, 4 + N_ERR)

    def forward(self, x):
        h = self.trunk(x)
        return self.bin(h).squeeze(-1), self.aux(h)


def auc(succ, fail):
    if not succ or not fail:
        return float("nan")
    w = t = 0.0
    for a in succ:
        for b in fail:
            if a > b: w += 1
            elif a == b: t += 1
    return (w + 0.5 * t) / (len(succ) * len(fail))


def main() -> int:
    from transformers import AutoModel, AutoTokenizer

    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    encoder = AutoModel.from_pretrained("microsoft/unixcoder-base").to("cuda").eval()
    for p in encoder.parameters():
        p.requires_grad_(False)

    rows = json.loads(POOL_MD.read_text())
    per_test = json.loads(PER_TEST.read_text())
    # Supervisor principal : binaire du pool (44/113 vrais, verdicts chaînés).
    # Yu-aux aux : per-test (4 bits + 15 erreurs). Jamais l'inverse — l'auxiliare
    # trop riche prédit la sortie tout seul (cf. Yu §2.3, aux-random).
    #

    # ---------- pré-embedding du pool + mutants
    print("embedding du pool + mutants…", flush=True)
    E_s, E_d, E_dm = [], [], []
    y_bin, y_aux, tasks = [], [], []
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
        y_bin.append(r["y"])  # verdict binaire officiel (44/113), protocole chaîné
        tasks.append(r["task"])
        E_s.append(r["state"]); E_d.append(r["diff"])
        E_dm.append(make_mutants(r["diff"], 3))
    # embed
    from itertools import chain
    E_s = batched_embed(E_s, encoder, tok)
    E_d = batched_embed(E_d, encoder, tok)
    flat_mut = list(chain.from_iterable(E_dm))
    E_mut = batched_embed(flat_mut, encoder, tok).view(-1, 3, E_d.shape[-1])

    def norm_t(A):
        return A / (A.norm(dim=-1, keepdim=True) + 1e-9)
    E_s, E_d, E_mut = norm_t(E_s), norm_t(E_d), norm_t(E_mut)

    X = torch.cat([E_s, E_d], dim=-1)
    y_bin = torch.tensor(y_bin, dtype=torch.float32)
    y_aux = torch.tensor(y_aux, dtype=torch.float32)
    tasks = np.array(tasks)
    print(f"trainable: {X.shape} | y_bin {y_bin.mean():.3f} ({int(y_bin.sum())}/{len(y_bin)})",
          flush=True)

    # ---------- LOAO
    uniq = sorted(set(tasks.tolist()))
    succ_scores, fail_scores = [], []
    fold_res = []
    for held in uniq:
        te = tasks == held
        tr = ~te
        if tr.sum() < 20:
            continue
        head = Head().to("cuda")
        opt = torch.optim.Adam(head.parameters(), lr=3e-3, weight_decay=1e-4)
        Xtr, ytr = X[tr].cuda(), y_bin[tr].cuda()
        atr = y_aux[tr].cuda()
        # X_mut = même canal que X mais avec diff remplacé par mutant0 (113×1536)
        X_mut = torch.cat([E_s, norm_t(E_mut[:, 0])], dim=-1)
        for ep in range(120):
            head.train(); opt.zero_grad()
            b, a = head(Xtr)
            lb = nn.functional.binary_cross_entropy_with_logits(b, ytr)
            la = nn.functional.mse_loss(torch.sigmoid(a), atr)
            # consistance bisimulation : mutant ≈ original dans le latent de la tête
            h_real = head.trunk(Xtr).detach()
            h_muts = head.trunk(X_mut[tr].cuda())
            lh = nn.functional.mse_loss(h_muts, h_real)
            loss = lb + 0.5 * la + 0.3 * lh
            loss.backward(); opt.step()
        head.eval()
        with torch.no_grad():
            b, _ = head(X[te].cuda())
            p = torch.sigmoid(b).cpu().numpy()
        for idx, pval in zip(np.where(te)[0], p):
            (succ_scores if y_bin[idx] == 1 else fail_scores).append(float(pval))
            fold_res.append({"task": held, "p": float(pval), "y": int(y_bin[idx])})

    a = auc(succ_scores, fail_scores)
    correct = sum(1 for f in fold_res if (f["p"] >= 0.5) == bool(f["y"]))
    n = len(fold_res)
    acc = correct / n
    import math as _m
    def wilson(k, n):
        z = 1.96; p = k / n; den = 1 + z*z/n
        c = (p + z*z/(2*n)) / den
        h = (z * _m.sqrt(p*(1-p)/n + z*z/(4*n*n))) / den
        return max(0, c-h), min(1, c+h)
    lo, hi = wilson(correct, n)
    print("\n===== RÉSULTAT LOAO (tête entraînée, encodeur gelé) =====")
    print(f"n={n} folds | acc {acc:.3f} Wilson95 [{lo:.3f},{hi:.3f}] | AUC {a:.3f}")
    print(f"succès moy {np.mean(succ_scores):.3f} (n={len(succ_scores)}) vs "
          f"échecs {np.mean(fail_scores):.3f} (n={len(fail_scores)})")
    maj = max(sum(1 for f in fold_res if f["y"] == 1), sum(1 for f in fold_res if f["y"] == 0)) / n
    print(f"majority baseline: {maj:.3f}")
    (ROOT / "data/landing/act2-pilot/head-eval.json").write_text(
        json.dumps({"n": n, "acc": acc, "wilson95": [lo, hi], "auc": a,
                    "majority": maj, "folds": fold_res}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
