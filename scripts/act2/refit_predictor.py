#!/usr/bin/env python3
"""Refit du predictor act2 sur les vrais patchs issus de la fenêtre pilote 2026-08-07.

Moindre honnêteté statistique : 38 exemples uniques dédupliqués, label
f2p_binary — leave-one-out CV pour l'estimation, pas de holdout théâtral.
Artifact = même format que v0 (predictor.json) : hashé, pinné, traçable.
"""

from __future__ import annotations

import json
import math
import random
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / "data" / "landing" / "act2-pilot" / "refit-pool.json"
sys.path.insert(0, str(ROOT / "packages" / "gate" / "src"))
from gate._murmur3 import murmur3_32  # noqa: E402

N_FEATURES = 2**12
PROJ = "predictor act2-v1"


def featurize_sparse(doc: str, n: int = N_FEATURES) -> dict[int, float]:
    import re as _re
    counts: dict[int, float] = {}
    for tok in _re.findall(r"(?u)\b\w\w+\b", doc.lower()):
        h = murmur3_32(tok.encode())
        signed = h - (1 << 32) if h >= (1 << 31) else h
        col = abs(signed) % n
        counts[col] = counts.get(col, 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in counts.values()))
    return {k: v / norm for k, v in counts.items()} if norm else {}


def fit_sgd(samples: list[tuple[dict[int, float], int]], *, epochs: int = 40,
            lr: float = 0.3, l2: float = 1e-4, seed: int = 6769) -> tuple[list[float], float]:
    w = [0.0] * N_FEATURES
    b = 0.0
    rng = random.Random(seed)
    n_pos = sum(y for _, y in samples)
    b = math.log((n_pos + 0.5) / (len(samples) - n_pos + 0.5))  # prior intercept
    for _ in range(epochs):
        rng.shuffle(samples)
        for x, y in samples:
            z = b + sum(w[i] * v for i, v in x.items())
            p = 1 / (1 + math.exp(-z)) if z >= 0 else (math.exp(z) / (1 + math.exp(z)))
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


def main() -> int:
    pool = json.loads(POOL.read_text())
    samples = [(featurize_sparse(x["patch"]), 1 if x["f2p_binary"] else 0)
               for x in pool if x.get("patch")]
    n, n_pos = len(samples), sum(y for _, y in samples)
    print(f"pool: {n} exemples ({n_pos} positifs, {n - n_pos} négatifs)")

    # leave-one-out
    correct = 0
    for i in range(n):
        tr = samples[:i] + samples[i + 1:]
        w, b = fit_sgd(list(tr))
        p = predict(w, b, samples[i][0])
        if (p >= 0.5) == bool(samples[i][1]):
            correct += 1
    acc = correct / n
    lo, hi = wilson(correct, n)
    print(f"LOO accuracy: {correct}/{n} = {acc:.3f}  Wilson95 [{lo:.3f}, {hi:.3f}]")
    maj = max(n_pos, n - n_pos) / n
    print(f"majority-class baseline: {maj:.3f}  — en dessous = predictor inutile")

    # fit final sur tout
    w, b = fit_sgd(samples)
    artifact = {
        "predictor_version": "probe-predictor-act2-v1",
        "corpus_version": "refit-pool-2026-08-07",
        "measured": {
            "n_pool": n, "n_positive": n_pos,
            "loo_accuracy": acc, "loo_wilson95": [lo, hi],
            "majority_baseline": maj,
            "source": "Act II pilot windows v2+v3 (real diffs, real F2P)",
            "posture": "measured on tiny n, advisory only",
        },
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "alternate_sign": False,
                       "norm": "l2", "lowercase": True, "token_pattern": r"\b\w\w+\b",
                       "n_features": N_FEATURES},
        "model": {"intercept": b, "coefficients": w},
    }
    out = ROOT / "governance" / "act2" / "arm-artifacts" / "predictor-act2-v1.json"
    payload = json.dumps(artifact, indent=1, sort_keys=True) + "\n"
    out.write_text(payload)
    print(f"artifact: {out}  sha256 {sha256(payload.encode()).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
