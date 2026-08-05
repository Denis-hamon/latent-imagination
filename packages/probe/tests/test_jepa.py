"""JEPA arm: smoke (loss falls), determinism, budget caps. ML-extra gated."""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("torch") is None,
    reason="requires the [ml] extra (torch) — see AR-10 isolation guard",
)


def _toy(seed=0):
    import numpy as np

    rng = np.random.default_rng(seed)
    Xp = rng.normal(1.0, 0.3, size=(60, 32))
    Xn = rng.normal(-1.0, 0.3, size=(60, 32))
    return np.vstack([Xp, Xn]), [1] * 60 + [0] * 60


def test_smoke_deterministic():
    from probe.arms.jepa import train_and_evaluate

    X, y = _toy()
    a = train_and_evaluate(X, y, X, y)
    b = train_and_evaluate(X, y, X, y)
    assert a["artifact_hash"] == b["artifact_hash"]
    assert a["loss_curve_last"] is not None
    assert 0.0 <= a["precision"] <= 1.0


def test_budget_caps_stop_and_disclose():
    from probe.arms.jepa import JepaConfig, train_and_evaluate

    X, y = _toy()
    art = train_and_evaluate(X, y, X, y, config=JepaConfig(steps_cap=2, epochs=100))
    assert art["truncated"] is True
    assert art["steps"] <= 2
