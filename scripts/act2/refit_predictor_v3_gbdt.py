#!/usr/bin/env python3
"""Precitor act2-v3: features de structure + contexte tâche, modèle GBDT stdlib.

Honnêtetés garde-fous — chacune est code, pas parole :
- LOTO (leave-one-task-out) : la tâche est hors du fold train, y compris pour le
  calcul des quantiles des features numériques.
- Tout est déterministe (seed fixe 6769). Mêmes données, mêmes poids.
- Zéro dépendance ML. L'artefact exporte des arbres, l'évaluateur est pur stdlib —
  la doctrine "aucune ML en serving" est préservée (recipe kind explicite).
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "gate" / "src"))
from gate._murmur3 import murmur3_32

N_HASH = 2**11

TOKEN = re.compile(r"(?u)\b\w\w+\b")
DIFF_LINE = re.compile(r"^(?P<sign>[+-])(?P<rest>.*)$", re.MULTILINE)
FILE_HDR = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
HUNK = re.compile(r"^@@ ", re.MULTILINE)


def hash_tokens(text: str, prefix: str) -> dict[int, float]:
    out: dict[int, float] = {}
    for tok in TOKEN.findall(text.lower()):
        h = murmur3_32((prefix + tok).encode())
        col = abs(h if h < 1 << 31 else h - (1 << 32)) % N_HASH
        out[col] = 1.0
    return out


def struct_feats(patch: str) -> dict[str, float]:
    added = removed = 0
    adds_import = removes_import = 0
    adds_def = removes_def = 0
    for m in DIFF_LINE.finditer(patch):
        if m.group("sign") == "+":
            added += 1
            r = m.group("rest")
            adds_import += int(bool(re.match(r"\s*(import|from)\b", r)))
            adds_def += int(bool(re.match(r"\s*def\b", r)))
        else:
            removed += 1
            r = m.group("rest")
            removes_import += int(bool(re.match(r"\s*(import|from)\b", r)))
            removes_def += int(bool(re.match(r"\s*def\b", r)))
    files = FILE_HDR.findall(patch)
    hunks = len(HUNK.findall(patch))
    deepest = max((f.count("/") for f in files), default=0)
    return {
        "n_added": float(added), "n_removed": float(removed),
        "n_files": float(len(files)), "n_hunks": float(hunks),
        "max_depth": float(deepest),
        "adds_import": float(adds_import), "removes_def": float(removes_def),
        "adds_def": float(adds_def), "removes_import": float(removes_import),
        "log_size": math.log1p(added + removed),
    }


# --- GBDT minimaliste, déterministe, stdlib -----------------------------------

def _candidate_columns(X: list[dict[int, float]], y_pred: list[float], y: list[float],
                       rng: random.Random, max_cols: int = 128) -> list[int]:
    """Top-K colonnes par |corr| avec le résiduel courant — pas de scan 2^22."""
    resid = [yi - pi for yi, pi in zip(y, y_pred)]
    scores: dict[int, float] = {}
    for xi, ri in zip(X, resid):
        for col, v in xi.items():
            scores[col] = scores.get(col, 0.0) + ri * v
    best = sorted(scores.items(), key=lambda kv: -abs(kv[1]))[:max_cols]
    cols = sorted(c for c, _ in best)
    rng.shuffle(cols)  # bris d'égalité déterministe
    return cols


def _fit_tree(X, resid, cols, depth, min_samples=4):
    n = len(resid)
    if depth == 0 or n < 2 * min_samples:
        return {"leaf": statistics.fmean(resid) if resid else 0.0}
    best_gain = 0.0
    best = None
    parent_mean = statistics.fmean(resid)
    for col in cols:
        vals = sorted({x.get(col, 0.0) for x in X})
        if len(vals) <= 1:
            continue
        th = max(vals) / 2 + min(vals) / 2 if len(vals) > 2 else vals[0] / 2 + vals[-1] / 2
        left = [r for x, r in zip(X, resid) if x.get(col, 0.0) <= th]
        right = [r for x, r in zip(X, resid) if x.get(col, 0.0) > th]
        if len(left) < min_samples or len(right) < min_samples:
            continue
        lm, rm = statistics.fmean(left), statistics.fmean(right)
        gain = len(left) * (lm - parent_mean) ** 2 + len(right) * (rm - parent_mean) ** 2
        if gain > best_gain:
            best_gain = gain
            best = (col, th, lm, rm)
    if best is None:
        return {"leaf": parent_mean}
    col, th, _, _ = best
    L = [i for i, x in enumerate(X) if x.get(col, 0.0) <= th]
    R = [i for i, x in enumerate(X) if x.get(col, 0.0) > th]
    Xl = [X[i] for i in L]; rl = [resid[i] for i in L]
    Xr = [X[i] for i in R]; rr = [resid[i] for i in R]
    return {"col": col, "th": th,
            "left": _fit_tree(Xl, rl, cols, depth - 1, min_samples),
            "right": _fit_tree(Xr, rr, cols, depth - 1, min_samples)}


def _tree_predict(tree, x):
    node = tree
    while "leaf" not in node:
        node = node["left"] if x.get(node["col"], 0.0) <= node["th"] else node["right"]
    return node["leaf"]


COL_OFFSET = 2**16  # réservé aux features structurales (col < COL_OFFSET)


def featurize_v3(patch: str, problem: str, f2p_names: list[str]) -> dict[int, float]:
    """struct features (cols < 2^16) + hashed namespaces 'D:'iff, 'P:'roblem, 'T:'ests."""
    x: dict[int, float] = {}
    for i, (_, v) in enumerate(sorted(struct_feats(patch).items())):
        x[i] = v
    for col, v in hash_tokens(patch, "D:").items():
        x[COL_OFFSET + col] = v
    for col, v in hash_tokens(problem[:1200], "P:").items():
        x[COL_OFFSET + N_HASH + col] = v
    for col, v in hash_tokens(";".join(f2p_names[:6]), "T:").items():
        x[COL_OFFSET + 2 * N_HASH + col] = v
    return x


def fit_gbdt(X, y, *, n_trees=48, depth=3, lr=0.1, seed=6769):
    rng = random.Random(seed)
    prior = sum(y) / len(y)
    b = math.log((prior + 0.5) / (1 - prior + 0.5))
    pred = [b] * len(y)
    trees = []
    for _ in range(n_trees):
        cols = _candidate_columns(X, pred, y, rng)
        tree = _fit_tree(X, [yi - pi for yi, pi in zip(y, pred)], cols, depth)
        trees.append(tree)
        for i, x in enumerate(X):
            pred[i] += lr * _tree_predict(tree, x)
    return {"prior": b, "lr": lr, "trees": trees}


def predict_gbdt(model, x) -> float:
    z = model["prior"] + model["lr"] * sum(_tree_predict(tr, x) for tr in model["trees"])
    return 1 / (1 + math.exp(-min(30, max(-30, z))))


def wilson(k, n, z0=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z0 * z0 / n
    c = (p + z0 * z0 / (2 * n)) / den
    half = (z0 * math.sqrt(p * (1 - p) / n + z0 * z0 / (4 * n * n))) / den
    return (max(0.0, c - half), min(1.0, c + half))


def main() -> int:
    raw = json.loads((ROOT / "data/landing/act2-pilot" / "refit-pool-v2.json").read_text())
    task_meta = {t["instance_id"]: t for t in json.loads(
        (ROOT / "data/landing/act2-pilot/extension-128/pilot-tasks.json").read_text())}
    task_meta.update({t["instance_id"]: t for t in json.loads(
        (ROOT / "data/landing/act2-pilot" / "pilot-tasks.json").read_text())})
    samples = []
    for x in raw:
        t = task_meta[x["task"]]
        samples.append({"task": x["task"], "y": x["y"],
                        "x": featurize_v3(x["patch"], t["problem"], t["f2p"])})
    tasks = sorted({s["task"] for s in samples})
    print(f"pool: {len(samples)} patchs | {len(tasks)} tâches | {sum(s['y'] for s in samples)} positifs")

    tp = tn = fp = fn = 0
    su: list[float] = []
    fa: list[float] = []
    probs: list[dict] = []
    for t in tasks:
        tr = [(s["x"], s["y"]) for s in samples if s["task"] != t]
        te = [s for s in samples if s["task"] == t]
        m = fit_gbdt([x for x, _ in tr], [y for _, y in tr])
        for s in te:
            p = predict_gbdt(m, s["x"])
            hyp = p >= 0.5
            tp += hyp and s["y"]; tn += not hyp and not s["y"]
            fp += hyp and not s["y"]; fn += not hyp and s["y"]
            (su if s["y"] else fa).append(p)
            probs.append({"task": t, "p": round(p, 4), "y": s["y"]})
    n = tp + tn + fp + fn
    acc = (tp + tn) / n
    lo, hi = wilson(tp + tn, n)
    maj = max(tp + fn, tn + fp) / n
    recall = tp / (tp + fn)
    prec = tp / (tp + fp) if fp + tp else 0.0
    gap = statistics.mean(su) - statistics.mean(fa)
    print(json.dumps({"v3_gbdt_loto": {"n": n, "tasks": len(tasks),
          "accuracy": round(acc, 4), "wilson95": [round(lo, 4), round(hi, 4)],
          "majority_baseline": round(maj, 4),
          "recall_positifs": round(recall, 3), "precision_positifs": round(prec, 3),
          "score_gap": round(gap, 4), "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn}}},
          indent=1))
    # artifact final (train sur TOUT le pool — c'est la forme qu'on épingle si adoptée)
    final = fit_gbdt([s["x"] for s in samples], [s["y"] for s in samples])
    artifact = {
        "predictor_version": "probe-predictor-act2-v3-gbdt",
        "recipe": {"kind": "gbdt-stdlib", "features": "struct10 + hashed D/P/T (murmur3, n=2^11*3)",
                   "n_trees": 48, "depth": 3, "lr": 0.1, "seed": 6769},
        "measured": {"protocol": "LOTO task-held-out", "n": n, "tasks": len(tasks),
                     "accuracy": acc, "wilson95": [lo, hi], "majority_baseline": maj,
                     "recall_positifs": recall, "precision_positifs": prec, "score_gap": gap},
        "model": final,
        "provenance": {"pool_sha256": sha256(
            (ROOT / "data/landing/act2-pilot/refit-pool-v2.json").read_bytes()).hexdigest()},
        "posture": "advisory only — LOTO measured, doctrine branch-iii",
    }
    out = ROOT / "governance/act2/arm-artifacts/predictor-act2-v3-gbdt.json"
    out.write_text(json.dumps(artifact, indent=1, sort_keys=True) + "\n")
    print("artifact:", out, "\nsha256", sha256(out.read_bytes()).hexdigest()[:16])
    (ROOT / "data/landing/act2-pilot/v3-loto-probs.json").write_text(
        json.dumps(probs, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
