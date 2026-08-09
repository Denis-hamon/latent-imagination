#!/usr/bin/env python3
"""E6 — auxiliaire multi-graine vs superviseur binaire seul (Yu Thm.1, version mesurée).

Question : à n=113, est-ce qu'un auxiliaire DENSE (multi-hot per-test : 4 bits pass +
15 classes d'erreur, densité 19) améliore la généralisation LOAO de la tête verdict,
par rapport au superviseur binaire seul ?

Contrôle strict — commun aux deux bras :
  - même features : X = [norm(E_state), norm(E_diff)] (uniXCoder gelé, npz existant)
  - même tête : MLP(1536→256)→1, mêmes hyperparamètres que train_energy_head.py
  - même LOAO (69 folds, tâche entière tenue dehors)
  - **même init par fold** (seed = hash(tâche)) : comparaison appariée, seule la loss change

Bras :
  A. binaire seul          : loss = BCE
  B. binaire + Yu multi-hot: loss = BCE + 0.5·MSE(sigmoid(aux), multi-hot)
  C. binaire + bisimulation: loss = BCE + 0.3·MSE(trunk(mutant), trunk(réel))
     — c'est le contraste isolé de la piste E1-synthèse (mutation-syntax), absent
     de l'addendum 08-07d où le terme était noyé dans une loss à 3 composantes.

(Durée non capturée dans per-test.json → aux enrichi = bits + errclass, comme
l'addendum 08-07d ; c'est l'enrichissement disponible, noté honnêtement.)

Sortie : data/landing/act2-pilot/e6-aux-ablation.json
"""

from __future__ import annotations

import json
import math
import zlib
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"

import os
import sys
sys.path.insert(0, str(ROOT / "scripts" / "act2"))
from train_energy_head import make_mutants  # même générateur que la tête 08-07d

ERR_CLASSES = ["AssertionError", "TypeError", "ValueError", "KeyError", "AttributeError",
               "NameError", "ImportError", "ModuleNotFoundError", "SyntaxError",
               "IndentationError", "IndexError", "RecursionError", "TimeoutError",
               "unknown", "apply-failed"]
N_ERR = len(ERR_CLASSES)


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


def wilson(k: int, n: int) -> tuple[float, float]:
    z = 1.96
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return max(0.0, c - h), min(1.0, c + h)


def auc(succ, fail) -> float:
    if not succ or not fail:
        return float("nan")
    w = t = 0.0
    for a in succ:
        for b in fail:
            if a > b:
                w += 1
            elif a == b:
                t += 1
    return (w + 0.5 * t) / (len(succ) * len(fail))


def norm(A: np.ndarray) -> np.ndarray:
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def main() -> int:
    torch.manual_seed(6769)
    np.random.seed(6769)

    rows = json.loads((PILOT / "latent-pool.json").read_text())
    per_test = json.loads((PILOT / "per-test.json").read_text())
    d = np.load(PILOT / "latent-pool.npz")
    E_s, E_d = norm(d["E_state"]), norm(d["E_diff"])

    X_l, yb_l, ya_l, tk_l = [], [], [], []
    for i, r in enumerate(rows):
        key = f"{r['campaign']}|{r['task']}|{r['arm']}"
        pt = per_test.get(key)
        if pt is None:
            continue
        tests = pt[:4]
        n = len(tests)
        bits = [1 if t["passed"] else 0 for t in tests] + [0] * (4 - n)
        errs = Counter(t.get("errclass", "unknown") for t in tests if not t["passed"])
        errvec = [errs.get(e, 0) / max(1, n) for e in ERR_CLASSES]
        ya_l.append(bits + errvec)
        yb_l.append(int(r["y"]))
        tk_l.append(r["task"])
        X_l.append(np.concatenate([E_s[i], E_d[i]]))

    X = torch.tensor(np.array(X_l), dtype=torch.float32)
    y_bin = torch.tensor(yb_l, dtype=torch.float32)
    y_aux = torch.tensor(ya_l, dtype=torch.float32)
    tasks = np.array(tk_l)
    kept = [i for i, r in enumerate(rows)
            if per_test.get(f"{r['campaign']}|{r['task']}|{r['arm']}") is not None]
    print(f"join per-test : {X.shape[0]}/{len(rows)} | pos {int(y_bin.sum())}")

    # mutants pour le bras bisimulation (E1-synthèse) — unsupervisé, LOAO-safe
    print("mutants + embedding (uniXCoder gelé, CPU)…", flush=True)
    from transformers import AutoModel, AutoTokenizer
    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    enc = AutoModel.from_pretrained("microsoft/unixcoder-base").eval()
    mut_texts = [make_mutants(rows[i]["diff"], k=1)[0] for i in kept]
    E_m = []
    with torch.no_grad():
        for i in range(0, len(mut_texts), 16):
            tb = tok(mut_texts[i:i + 16], padding=True, truncation=True, max_length=512,
                     return_tensors="pt")
            E_m.append(enc(**tb).last_hidden_state[:, 0].numpy())
    E_mn = norm(np.concatenate(E_m))
    kept_s = np.array([E_s[i] for i in kept])
    X_mut = torch.tensor(np.concatenate([kept_s, E_mn], axis=1), dtype=torch.float32)

    uniq = sorted(set(tasks.tolist()))
    res = {"bin": {"p": [], "y": []}, "bin_aux": {"p": [], "y": []},
           "bin_bisim": {"p": [], "y": []}}
    for held in uniq:
        te = tasks == held
        tr = ~te
        if tr.sum() < 20:
            continue
        Xtr, ytr, atr = X[tr], y_bin[tr], y_aux[tr]
        for arm in ("bin", "bin_aux", "bin_bisim"):
            torch.manual_seed(zlib.crc32(held.encode()))  # même init par fold et par bras
            head = Head()
            opt = torch.optim.Adam(head.parameters(), lr=3e-3, weight_decay=1e-4)
            for _ in range(120):
                head.train()
                opt.zero_grad()
                b, a = head(Xtr)
                loss = nn.functional.binary_cross_entropy_with_logits(b, ytr)
                if arm == "bin_aux":
                    loss = loss + 0.5 * nn.functional.mse_loss(torch.sigmoid(a), atr)
                elif arm == "bin_bisim":
                    h_real = head.trunk(Xtr).detach()
                    h_muts = head.trunk(X_mut[tr])
                    loss = loss + 0.3 * nn.functional.mse_loss(h_muts, h_real)
                loss.backward()
                opt.step()
            head.eval()
            with torch.no_grad():
                b, _ = head(X[te])
                p = torch.sigmoid(b).numpy()
            res[arm]["p"].extend(p.tolist())
            res[arm]["y"].extend(y_bin[te].numpy().astype(int).tolist())
        print(f"fold {held[:48]:48s} done", flush=True)

    out = {"n_folds_n": len(res["bin"]["y"]), "branches": {}}
    for arm, r in res.items():
        ys, ps = np.array(r["y"]), np.array(r["p"])
        k = int(((ps >= 0.5).astype(int) == ys).sum())
        n = len(ys)
        lo, hi = wilson(k, n)
        out["branches"][arm] = {
            "acc": k / n, "wilson95": [lo, hi],
            "auc": auc(ps[ys == 1].tolist(), ps[ys == 0].tolist()),
            "mean_p_succ": float(ps[ys == 1].mean()),
            "mean_p_fail": float(ps[ys == 0].mean()),
        }

    ys = np.array(res["bin"]["y"])
    from math import comb

    def mcnemar(arm_a: str, arm_b: str) -> dict:
        ok_a = (np.array(res[arm_a]["p"]) >= 0.5).astype(int) == ys
        ok_b = (np.array(res[arm_b]["p"]) >= 0.5).astype(int) == ys
        bb = int((ok_a & ~ok_b).sum())
        cc = int((~ok_a & ok_b).sum())
        n_disc = bb + cc
        pval = (2 * min(sum(comb(n_disc, i) for i in range(0, min(bb, cc) + 1)),
                        sum(comb(n_disc, i) for i in range(max(bb, cc), n_disc + 1)))
                / 2 ** n_disc) if n_disc else 1.0
        return {f"b_{arm_a}_only": bb, f"c_{arm_b}_only": cc, "p_exact": min(1.0, pval)}

    out["mcnemar_bin_vs_aux"] = mcnemar("bin", "bin_aux")
    out["mcnemar_bin_vs_bisim"] = mcnemar("bin", "bin_bisim")
    out["majority_baseline"] = max(int(ys.sum()), int((1 - ys).sum())) / len(ys)

    print(f"\n===== E6+E1s — ablations auxiliaires, n={out['n_folds_n']} "
          f"(majorité {out['majority_baseline']:.3f}) =====")
    for arm, m in out["branches"].items():
        print(f"{arm:10s} | acc {m['acc']:.3f} [{m['wilson95'][0]:.3f},{m['wilson95'][1]:.3f}]"
              f" | AUC {m['auc']:.3f} | p_succ {m['mean_p_succ']:.3f} vs p_fail {m['mean_p_fail']:.3f}")
    print(f"McNemar bin vs aux   : {out['mcnemar_bin_vs_aux']}")
    print(f"McNemar bin vs bisim : {out['mcnemar_bin_vs_bisim']}")

    (PILOT / "e6-aux-ablation.json").write_text(json.dumps(out, indent=1))
    print(f"\nartefact : {PILOT / 'e6-aux-ablation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
