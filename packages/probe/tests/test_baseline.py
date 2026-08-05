"""Baseline arm: determinism, budget caps, hand-computed metrics."""

from __future__ import annotations

import numpy as np
import pytest
from probe.arms.baseline import (
    ArmConfig,
    BudgetWallExceeded,
    asymmetry,
    train_and_evaluate,
)


def _toy(seed=0):
    rng = np.random.default_rng(seed)
    Xp = rng.normal(1.0, 0.3, size=(40, 8))
    Xn = rng.normal(-1.0, 0.3, size=(60, 8))
    X = np.vstack([Xp, Xn])
    y = [1] * 40 + [0] * 60
    return X, y


def test_deterministic_same_seed():
    X, y = _toy()
    a = train_and_evaluate(X, y, X, y)
    b = train_and_evaluate(X, y, X, y)
    assert a.artifact_hash == b.artifact_hash
    assert a.precision == b.precision


def test_perfect_separation_metrics():
    X, y = _toy()
    r = train_and_evaluate(X, y, X, y)
    # sanity against the arm itself: it should learn this toy
    assert r.precision >= 0.95
    assert r.n_pred_positive > 0
    assert r.n_eval == 100


def test_steps_cap_raises():
    X, y = _toy()
    with pytest.raises(BudgetWallExceeded, match="steps"):
        train_and_evaluate(X, y, X, y, config=ArmConfig(steps_cap=1))


def test_asymmetry_math():
    # bar = 0.02 / 0.0225 = 0.8889
    assert asymmetry(0.95, 0.0025, 0.0200) > 0
    assert asymmetry(0.50, 0.0025, 0.0200) == 0.0
