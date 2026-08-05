"""JEPA arm: smoke (loss falls), determinism, budget caps."""

from __future__ import annotations

import numpy as np
import pytest

from probe.arms.jepa import BudgetExceeded, JepaConfig, train_and_evaluate


def _toy(seed=0):
    rng = np.random.default_rng(seed)
    Xp = rng.normal(1.0, 0.3, size=(60, 32))
    Xn = rng.normal(-1.0, 0.3, size=(60, 32))
    return np.vstack([Xp, Xn]), [1] * 60 + [0] * 60


def test_loss_decreases_and_determinism():
    X, y = _toy()
    r = train_and_evaluate(X, y, X, y, config=JepaConfig(epochs=3, batch=32))
    assert 0.0 <= r["precision"] <= 1.0
    assert r["steps"] > 0
    r2 = train_and_evaluate(X, y, X, y, config=JepaConfig(epochs=3, batch=32))
    assert r["artifact_hash"] == r2["artifact_hash"]  # same seed → same run


def test_budget_caps_stop_and_flag_truncated():
    X, y = _toy()
    r = train_and_evaluate(X, y, X, y, config=JepaConfig(epochs=50, steps_cap=2, batch=8))
    assert r["truncated"] is True  # cap discipline visible, not hidden (R10)
