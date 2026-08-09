#!/usr/bin/env python3
"""E3 — macro-action hiérarchique : chunk logique du diff (Zhang 26 / HWM sur code).

Question : une lecture à DEUX NIVEAUX de l'action (bas = les hunks du diff, haut =
l'intention, dim = 768 ≪ espace token) capture-t-elle plus de signal verdict que la
lecture plate (E4 : CLS du diff entier) ?

Construction (identique côté candidat et gold) :
  - split du diff en hunks (@@ … @@), chaque hunk embeddé séparément (uniXCoder gelé)
  - bottom : z_j = CLS(hunk_j) ; top : intention = mean_pool(norm(z_j))
  - composition : c_macro = norm(E_state + meanpool)           [top : l'intention]
    (contrôle plat : c_flat = norm(E_state + CLS(diff entier)) — recette E4)

Énergie macro : 1 − cos(c_macro_candidat, c_macro_gold) ; même règle de seuil
médiane-train par fold, même LOAO (69 tâches), McNemar apparié vs énergie plate.
Bras secondaire bottom-only agrégé : min/mean des distances hunk↔hunk-gold (contrôle
que le gain éventuel vient de l'intention, pas du simple découpage).

Sortie : data/landing/act2-pilot/e3-macro-action.json
"""

from __future__ import annotations

import json
import math
import os
import re
from itertools import chain
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"

HUNK = re.compile(r"^@@ .*?@@", re.M)


def split_hunks(diff: str) -> list[str]:
    """Découpe un diff unifié en hunks ; diff sans hunk → [diff entier]."""
    marks = [m.start() for m in HUNK.finditer(diff)]
    if not marks:
        return [diff]
    # préambule (headers diff --git/index/---/+++) rattaché au premier hunk
    starts = [marks[0]] if marks[0] == 0 else [marks[0]]
    hunks = []
    bounds = marks + [len(diff)]
    for i, s in enumerate(marks):
        e = bounds[i + 1]
        piece = (diff[:s] if i == 0 else "") + diff[s:e]
        hunks.append(piece)
    return [h for h in hunks if h.strip()] or [diff]


def norm(A: np.ndarray) -> np.ndarray:
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


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


def batched_embed(texts, model, tok, bs=16):
    out = []
    for i in range(0, len(texts), bs):
        tb = tok(texts[i:i + bs], padding=True, truncation=True, max_length=512,
                 return_tensors="pt")
        with torch.no_grad():
            out.append(model(**tb).last_hidden_state[:, 0].numpy())
    return np.concatenate(out)


def loao_eval(energies: np.ndarray, y: np.ndarray, tasks: np.ndarray) -> dict:
    """Règle E4 : seuil = médiane des énergies train du fold. Retourne stats + preds."""
    uniq = sorted(set(tasks.tolist()))
    preds, ys, es = [], [], []
    for held in uniq:
        te = tasks == held
        tr = ~te
        if tr.sum() < 20:
            continue
        thr = np.median(energies[tr])
        idx = np.where(te)[0]
        preds.extend((energies[idx] < thr).astype(int).tolist())
        ys.extend(y[idx].tolist())
        es.extend(energies[idx].tolist())
    ys, preds, es = np.array(ys), np.array(preds), np.array(es)
    k = int((preds == ys).sum())
    lo, hi = wilson(k, len(ys))
    return {"acc": k / len(ys), "wilson95": [lo, hi],
            "auc": auc((-es)[ys == 1].tolist(), (-es)[ys == 0].tolist()),
            "mean_E_succ": float(es[ys == 1].mean()),
            "mean_E_fail": float(es[ys == 0].mean()),
            "preds": preds.tolist(), "ys": ys.tolist()}


def main() -> int:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    rows = json.loads((PILOT / "latent-pool.json").read_text())
    d = np.load(PILOT / "latent-pool.npz")
    E_s, E_d, E_g = norm(d["E_state"]), norm(d["E_diff"]), norm(d["E_goal"])
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    n = len(rows)

    print("split hunks + embedding (uniXCoder gelé, CPU)…", flush=True)
    from transformers import AutoModel, AutoTokenizer
    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    enc = AutoModel.from_pretrained("microsoft/unixcoder-base").eval()

    d_hunks = [split_hunks(r["diff"]) for r in rows]
    g_hunks = [split_hunks(r["gold"]) for r in rows]
    n_h = [len(h) for h in d_hunks]
    print(f"hunks/diff : médiane {int(np.median(n_h))}, max {max(n_h)}, "
          f"mono-hunk {sum(1 for x in n_h if x == 1)}/{n}")

    E_dh = norm(batched_embed(list(chain.from_iterable(d_hunks)), enc, tok))
    E_gh = norm(batched_embed(list(chain.from_iterable(g_hunks)), enc, tok))

    # regroupe par échantillon
    def regroup(E_flat, hunks):
        out, i = [], 0
        for hs in hunks:
            out.append(E_flat[i:i + len(hs)])
            i += len(hs)
        return out
    Z_d, Z_g = regroup(E_dh, d_hunks), regroup(E_gh, g_hunks)

    # intention = mean pool des hunks normés (top level, dim 768)
    I_d = norm(np.stack([z.mean(0) for z in Z_d]))
    I_g = norm(np.stack([z.mean(0) for z in Z_g]))

    # --- bras flat (contrôle E4)
    c_flat_d, c_flat_g = norm(E_s + E_d), norm(E_s + E_g)
    E_flat = 1.0 - (c_flat_d * c_flat_g).sum(-1)

    # --- bras macro top : intention hiérarchique
    c_mac_d, c_mac_g = norm(E_s + I_d), norm(E_s + I_g)
    E_macro = 1.0 - (c_mac_d * c_mac_g).sum(-1)

    # --- bras bottom-only : agrégat hunk↔hunk-gold (max de cos = hunk le plus proche)
    E_bot = np.array([1.0 - float((Z_d[i] @ Z_g[i].T).max()) for i in range(n)])

    res = {"flat": loao_eval(E_flat, y, tasks),
           "macro_top": loao_eval(E_macro, y, tasks),
           "bottom_only": loao_eval(E_bot, y, tasks)}

    # McNemar apparié macro vs flat
    ys = np.array(res["flat"]["ys"])
    ok_f = np.array(res["flat"]["preds"]) == ys
    ok_m = np.array(res["macro_top"]["preds"]) == ys
    b = int((ok_f & ~ok_m).sum())
    c = int((~ok_f & ok_m).sum())
    n_disc = b + c
    pval = (2 * min(sum(math.comb(n_disc, i) for i in range(0, min(b, c) + 1)),
                    sum(math.comb(n_disc, i) for i in range(max(b, c), n_disc + 1)))
            / 2 ** n_disc) if n_disc else 1.0

    out = {"n": n, "hunks_per_diff_median": int(np.median(n_h)),
           "branches": {k: {kk: vv for kk, vv in v.items() if kk not in ("preds", "ys")}
                        for k, v in res.items()},
           "mcnemar_macro_vs_flat": {"b_flat_only": b, "c_macro_only": c,
                                     "p_exact": min(1.0, pval)},
           "majority_baseline": max(int(y.sum()), int((1 - y).sum())) / n}

    print(f"\n===== E3 — macro-action hiérarchique, n={n} "
          f"(majorité {out['majority_baseline']:.3f}) =====")
    for k, m in out["branches"].items():
        print(f"{k:12s} | acc {m['acc']:.3f} [{m['wilson95'][0]:.3f},{m['wilson95'][1]:.3f}]"
              f" | AUC {m['auc']:.3f} | E_succ {m['mean_E_succ']:.4f} vs E_fail {m['mean_E_fail']:.4f}")
    print(f"McNemar macro vs flat : b={b} c={c} p={min(1.0, pval):.3f}")

    (PILOT / "e3-macro-action.json").write_text(json.dumps(out, indent=1))
    print(f"\nartefact : {PILOT / 'e3-macro-action.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
