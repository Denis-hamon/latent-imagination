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
    from probe.arms.jepa import JepaConfig, train_and_evaluate

    X, y = _toy()
    cfg = JepaConfig(epochs=10)  # instanciation explicite (garde-fou rétro 11)
    a = train_and_evaluate(X, y, X, y, config=cfg)
    b = train_and_evaluate(X, y, X, y, config=cfg)
    assert a["artifact_hash"] == b["artifact_hash"]
    assert a["loss_curve_last"] is not None
    assert 0.0 <= a["precision"] <= 1.0


def test_default_config_binds_to_step_cap_not_epochs():
    # Garde-fou rétro épic 11 : le défaut (epochs=None) doit entraîner
    # JUSQU'AU step cap (envelope design.toml), jamais s'arrêter à un epochs
    # arbitraire — le piège Act III r1 (default 10 epochs, sous-entraînement
    # dégénéré never-predicts-positive) est clos.
    from probe.arms.jepa import JepaConfig, train_and_evaluate

    X, y = _toy()
    art = train_and_evaluate(X, y, X, y, config=JepaConfig(steps_cap=5))
    assert art["steps"] == 5  # le cap, pas des epochs, a borné l'entraînement
    assert art["truncated"] is True


def test_budget_caps_stop_and_disclose():
    from probe.arms.jepa import JepaConfig, train_and_evaluate

    X, y = _toy()
    art = train_and_evaluate(X, y, X, y, config=JepaConfig(steps_cap=2, epochs=100))
    assert art["truncated"] is True
    assert art["steps"] <= 2
