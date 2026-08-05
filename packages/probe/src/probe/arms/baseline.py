"""Baseline arm — the boring one. Logistic regression on frozen features,
identical budget manifest, anchors its own result.

Sandbag audit surface (UJ-2): every choice is in the manifest; nothing tuned
after seeing eval metrics.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


class BudgetWallExceeded(Exception):
    code = "LI-PROBE-001"


@dataclass(frozen=True)
class ArmConfig:
    seed: int = 20260805
    c_value: float = 1.0
    max_iter: int = 2000
    steps_cap: int = 5_000
    wall_clopen_s: float = 30 * 60.0


@dataclass(frozen=True)
class ArmResult:
    precision: float
    recall: float
    f1: float
    n_pred_positive: int
    n_eval: int
    asymmetry_score: float
    cost_usd: float
    wall_s: float
    config: ArmConfig
    artifact_hash: str


def asymmetry(precision: float, cost_exec: float, cost_regen: float) -> float:
    """The economic score per the registered bar formula.
    Net positive iff precision > cost_regen / (cost_regen + cost_exec)."""
    bar = cost_regen / (cost_regen + cost_exec)
    return precision * (cost_regen - cost_exec) if precision > bar else 0.0


def train_and_evaluate(
    X_train: Any,
    y_train: list[int],
    X_eval: Any,
    y_eval: list[int],
    *,
    config: ArmConfig | None = None,
    budget_guard=None,
) -> ArmResult:
    from probe.embeddings import _load  # the extra-check

    _load()
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score, precision_score, recall_score

    config = config or ArmConfig()
    t0 = time.time()
    model = LogisticRegression(C=config.c_value, max_iter=config.max_iter, random_state=config.seed, class_weight="balanced")
    steps = 0
    model.fit(X_train, y_train)
    steps = int(getattr(model, "n_iter_", [0])[0])
    if steps > config.steps_cap:
        raise BudgetWallExceeded(f"steps {steps} > cap {config.steps_cap}")
    wall = time.time() - t0
    if wall > config.wall_clopen_s:
        raise BudgetWallExceeded(f"wall {wall:.0f}s > cap {config.wall_clopen_s:.0f}s")

    pred = model.predict(X_eval)
    n_pos = int(pred.sum())
    p = float(precision_score(y_eval, pred, zero_division=0.0))
    r = float(recall_score(y_eval, pred, zero_division=0.0))
    f1 = float(f1_score(y_eval, pred, zero_division=0.0))
    cost = 0.0  # CPU-seconds don't bill; the cost_usd axis lives in campaign manifests
    sc = asymmetry(p, 0.0025, 0.0200)
    art = {
        "C": config.c_value,
        "seed": config.seed,
        "n_iter": steps,
        "precision": p,
        "recall": r,
        "f1": f1,
    }
    art_hash = sha256(json.dumps(art, sort_keys=True).encode()).hexdigest()
    return ArmResult(p, r, f1, n_pos, len(y_eval), sc, cost, wall, config, art_hash)
