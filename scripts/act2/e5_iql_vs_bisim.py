#!/usr/bin/env python3
"""E5 — la métrique expectile (Destrade, d ≈ −V) coïncide-t-elle avec la métrique
bisimulation (Toso) sur nos patches ?  — équivalence non démontrée dans la littérature.

Deux distances par échantillon, toutes deux honnêtes :

  d_IQL  : valeur apprise par régression EXPECTILE (τ=0.9 ; contrôle τ=0.5 = moyenne)
           de y(F2P) sur X=[norm(E_state), norm(E_diff)], MLP(1536→256→1),
           loss asymétrique w·r² (w=τ si r>0 sinon 1−τ). Prédictions LOAO hors-pli
           (une tâche entière dehors à chaque fold) → distance au but = −V̂.

  d_bisim: couplage de surface du diff au renommage d'identifiants : moyenne sur
           3 mutants token-rename (make_mutants, même générateur que la tête 08-07d)
           de 1 − cos(emb(diff), emb(mutant)), uniXCoder gelé. Sans label →
           pas de pli nécessaire.

Mesure : Spearman(d_IQL, d_bisim) sur n=113 (IC95 Fisher), chaque métrique vs y (AUC).
  |ρ| élevé → les deux papiers capturent le même axe → pont "Destrade × Toso" supporté ;
  ρ ≈ 0    → deux axes orthogonaux → objectif fusionné NON supporté par nos données.

Sortie : data/landing/act2-pilot/e5-iql-vs-bisim.json
"""

from __future__ import annotations

import json
import math
import os
import sys
import zlib
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"

sys.path.insert(0, str(ROOT / "scripts" / "act2"))
from train_energy_head import make_mutants  # même générateur de mutants que la tête 08-07d


def norm(A: np.ndarray) -> np.ndarray:
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


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


def rankdata(a: np.ndarray) -> np.ndarray:
    """Rangs moyens (ties partagent) — suffisant pour Spearman."""
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    rx, ry = rankdata(x), rankdata(y)
    rho = float(np.corrcoef(rx, ry)[0, 1])
    n = len(x)
    z = math.atanh(max(-0.9999, min(0.9999, rho)))
    se = 1.0 / math.sqrt(n - 3)
    return rho, math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)


class VNet(nn.Module):
    def __init__(self, dim=1536, hid=256):
        super().__init__()
        self.f = nn.Sequential(nn.Linear(dim, hid), nn.GELU(), nn.LayerNorm(hid),
                               nn.Linear(hid, 1))

    def forward(self, x):
        return self.f(x).squeeze(-1)


def expectile_predict(Xtr, ytr, Xte, tau, seed, epochs=200):
    torch.manual_seed(seed)
    m = VNet()
    opt = torch.optim.Adam(m.parameters(), lr=1e-3, weight_decay=1e-4)
    for _ in range(epochs):
        opt.zero_grad()
        v = m(Xtr)
        r = ytr - v
        w = torch.where(r > 0, torch.full_like(r, tau), torch.full_like(r, 1.0 - tau))
        (w * r * r).mean().backward()
        opt.step()
    m.eval()
    with torch.no_grad():
        return m(Xte).numpy()


def batched_embed(texts, model, tok, bs=16):
    out = []
    for i in range(0, len(texts), bs):
        tb = tok(texts[i:i + bs], padding=True, truncation=True, max_length=512,
                 return_tensors="pt")
        with torch.no_grad():
            out.append(model(**tb).last_hidden_state[:, 0].numpy())
    return np.concatenate(out)


def main() -> int:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    rows = json.loads((PILOT / "latent-pool.json").read_text())
    d = np.load(PILOT / "latent-pool.npz")
    E_s, E_d = norm(d["E_state"]), norm(d["E_diff"])
    y = np.array([int(r["y"]) for r in rows], dtype=np.float32)
    tasks = np.array([r["task"] for r in rows])
    n = len(rows)
    X = torch.tensor(np.concatenate([E_s, E_d], axis=1), dtype=torch.float32)

    # ---------- d_bisim (unsupervisé, pas de pli)
    print("mutants + embedding (uniXCoder gelé, CPU)…", flush=True)
    from transformers import AutoModel, AutoTokenizer
    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    enc = AutoModel.from_pretrained("microsoft/unixcoder-base").eval()
    muts = [m for r in rows for m in make_mutants(r["diff"], k=3)]
    E_m = norm(batched_embed(muts, enc, tok)).reshape(n, 3, -1)
    d_bisim = (1.0 - (E_m * E_d[:, None, :]).sum(-1)).mean(1)  # (n,)

    # ---------- d_IQL : expectile LOAO, τ=0.9 et contrôle τ=0.5
    uniq = sorted(set(tasks.tolist()))
    V = {0.9: np.zeros(n), 0.5: np.zeros(n)}
    for held in uniq:
        te = tasks == held
        tr = ~te
        if tr.sum() < 20:
            continue
        seed = zlib.crc32(held.encode()) % (2 ** 31)
        for tau in V:
            V[tau][te] = expectile_predict(X[tr], torch.tensor(y[tr]), X[te], tau, seed)
        print(f"fold {held[:52]:52s} ok", flush=True)

    out = {"n": n, "d_bisim": {}, "d_IQL": {}, "spearman": {}}
    out["d_bisim"] = {
        "mean_succ": float(d_bisim[y == 1].mean()),
        "mean_fail": float(d_bisim[y == 0].mean()),
        "auc_couplage_vs_y": auc(d_bisim[y == 1].tolist(), d_bisim[y == 0].tolist()),
        # AUC du couplage : >0.5 ⇒ les succès se couplent PLUS à la surface (mal)
    }
    for tau, v in V.items():
        d_iql = -v
        out["d_IQL"][str(tau)] = {
            "mean_V_succ": float(v[y == 1].mean()),
            "mean_V_fail": float(v[y == 0].mean()),
            "auc_vs_y": auc(v[y == 1].tolist(), v[y == 0].tolist()),
        }
        rho, lo, hi = spearman(d_iql, d_bisim)
        out["spearman"][f"dIQL{tau}_vs_dbisim"] = {"rho": rho, "fisher95": [lo, hi]}

    print(f"\n===== E5 — expectile-metric vs bisim-metric, n={n} =====")
    print(f"d_bisim : succ {out['d_bisim']['mean_succ']:.4f} vs fail "
          f"{out['d_bisim']['mean_fail']:.4f} | AUC {out['d_bisim']['auc_couplage_vs_y']:.3f}")
    for tau in V:
        t = out["d_IQL"][str(tau)]
        s = out["spearman"][f"dIQL{tau}_vs_dbisim"]
        print(f"τ={tau} | AUC(V̂ vs y) {t['auc_vs_y']:.3f} | V̂ succ {t['mean_V_succ']:.3f} "
              f"vs fail {t['mean_V_fail']:.3f} | Spearman(d_IQL, d_bisim) {s['rho']:+.3f} "
              f"[{s['fisher95'][0]:+.3f},{s['fisher95'][1]:+.3f}]")

    (PILOT / "e5-iql-vs-bisim.json").write_text(json.dumps(out, indent=1))
    print(f"\nartefact : {PILOT / 'e5-iql-vs-bisim.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
