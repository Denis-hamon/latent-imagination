#!/usr/bin/env python3
"""Refit predictor act2-v2 sur le pool unifié (frozen32 + extension128), évalué LOTO.

Pas d'illusion LOO : les scores des patchs d'une même tâche sont corrélés
(même F2P visible) — la validation qui prouve la généralisation est
leave-one-TASK-out. Toutes les métriques affichées ici sont task-held-out.
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "gate" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "core-schema" / "src"))
from gate.predict import featurize

N_FEATURES = 2**12
POOL = ROOT / "data" / "landing" / "act2-pilot" / "refit-pool-v2.json"


def fs(doc: str) -> dict[int, float]:
    return {i: x for i, x in enumerate(featurize(doc, N_FEATURES)) if x}


def fit_sgd(samples: list[tuple[dict[int, float], int]], *, epochs: int = 40,
            lr: float = 0.3, l2: float = 1e-4, seed: int = 6769) -> tuple[list[float], float]:
    w = [0.0] * N_FEATURES
    rng = random.Random(seed)
    n_pos = sum(y for _, y in samples)
    b = math.log((n_pos + 0.5) / (len(samples) - n_pos + 0.5))
    for _ in range(epochs):
        rng.shuffle(samples)
        for x, y in samples:
            z = b + sum(w[i] * v for i, v in x.items())
            p = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
            g = p - y
            b -= lr * g
            for i, v in x.items():
                w[i] -= lr * (g * v + l2 * w[i])
    return w, b


def predict(w: list[float], b: float, x: dict[int, float]) -> float:
    z = b + sum(w[i] * v for i, v in x.items())
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def wilson(k: int, n: int, z0: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z0 * z0 / n
    c = (p + z0 * z0 / (2 * n)) / den
    half = (z0 * math.sqrt(p * (1 - p) / n + z0 * z0 / (4 * n * n))) / den
    return (max(0.0, c - half), min(1.0, c + half))


def loto_eval(samples: list[dict]) -> dict:
    tasks = sorted({s["task"] for s in samples})
    tp = tn = fp = fn = 0
    succ_scores: list[float] = []
    fail_scores: list[float] = []
    for t in tasks:
        tr = [(s["x"], s["y"]) for s in samples if s["task"] != t]
        te = [s for s in samples if s["task"] == t]
        w, b = fit_sgd(list(tr))
        for s in te:
            p = predict(w, b, s["x"])
            hyp = p >= 0.5
            tp += int(hyp and s["y"]); tn += int(not hyp and not s["y"])
            fp += int(hyp and not s["y"]); fn += int(not hyp and s["y"])
            (succ_scores if s["y"] else fail_scores).append(p)
    n = tp + tn + fp + fn
    acc = (tp + tn) / n
    lo, hi = wilson(tp + tn, n)
    maj = max(tp + fn, tn + fp) / n
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    delta = (statistics.mean(succ_scores) - statistics.mean(fail_scores)) if (succ_scores and fail_scores) else 0.0
    return {"n": n, "tasks": len(tasks), "accuracy": acc, "wilson95": [lo, hi],
            "majority_baseline": maj, "recall_positifs": recall, "precision_positifs": prec,
            "score_gap": delta, "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn}}


def main() -> int:
    raw = json.loads(POOL.read_text())
    samples = []
    for x in raw:
        samples.append({"task": x["task"], "x": fs(x["patch"]), "y": x["y"],
                        "campaign": x["campaign"]})
    print(f"pool: {len(samples)} patchs | {len({s['task'] for s in samples})} tâches | "
          f"{sum(s['y'] for s in samples)} positifs")
    met = loto_eval(samples)
    print(json.dumps(met, indent=1))
    # artifact final (train sur tout), même format que v0
    w, b = fit_sgd([(s["x"], s["y"]) for s in samples])
    artifact = {
        "predictor_version": "probe-predictor-act2-v2",
        "corpus_version": "refit-pool-v2-2026-08-07",
        "created_by": {"stage": "act2.refit", "date": "2026-08-07"},
        "measured": met,
        "source": "frozen32 3 windows + extension128 — LOTO-honest evaluation",
        "posture": "NO SIGNIFICANT SEPARATION if gap<0.05 — advisory only",
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "alternate_sign": False,
                       "norm": "l2", "lowercase": True, "token_pattern": r"\b\w\w+\b",
                       "n_features": N_FEATURES},
        "model": {"intercept": b, "coefficients": w},
    }
    out = ROOT / "governance" / "act2" / "arm-artifacts" / "predictor-act2-v2.json"
    out.write_text(json.dumps(artifact, indent=1, sort_keys=True) + "\n")
    from hashlib import sha256
    print(f"artifact: {out}\nsha256 {sha256(out.read_bytes()).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
