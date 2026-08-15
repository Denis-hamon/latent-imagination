"""Baseline arm: determinism, budget caps, hand-computed metrics.

ML-extra gated: skipped wholesale when numpy/sklearn aren't installed
(AR-10 isolation guard makes that the default surface)."""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("sklearn") is None,
    reason="requires the [ml] extra (see AR-10 isolation guard)",
)


def _train(*args, **kwargs):
    from probe.arms.baseline import train_and_evaluate

    return train_and_evaluate(*args, **kwargs)


def _toy(seed=0):
    import numpy as np

    rng = np.random.default_rng(seed)
    Xp = rng.normal(1.0, 0.3, size=(40, 8))
    Xn = rng.normal(-1.0, 0.3, size=(60, 8))
    X = np.vstack([Xp, Xn])
    y = [1] * 40 + [0] * 60
    return X, y


def test_deterministic_same_seed():
    X, y = _toy()
    a = _train(X, y, X, y)
    b = _train(X, y, X, y)
    assert a.artifact_hash == b.artifact_hash
    assert a.precision == b.precision


def test_perfect_separation_metrics():
    X, y = _toy()
    r = _train(X, y, X, y)
    assert r.precision >= 0.95
    assert r.n_pred_positive > 0
    assert r.n_eval == 100


def test_steps_cap_raises():
    from probe.arms.baseline import ArmConfig, BudgetWallExceeded

    X, y = _toy()
    with pytest.raises(BudgetWallExceeded, match="steps"):
        _train(X, y, X, y, config=ArmConfig(steps_cap=1))


def test_asymmetry_math():
    from probe.arms.baseline import asymmetry

    assert asymmetry(0.95, 0.0025, 0.0200) > 0
    assert asymmetry(0.50, 0.0025, 0.0200) == 0.0
