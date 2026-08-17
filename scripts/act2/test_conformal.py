"""Story 12.1 — lib conforme (conformal_tau) : couverture garantie, honest-emptiness.

Hermétique (numpy seul, données synthétiques) : prouve la mécanique de seuil,
pas le pool réel. Invariants exacts (leçon rétro épic 7 : pas d'assertion lâche).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

_SPEC = importlib.util.spec_from_file_location(
    "conformal", Path(__file__).resolve().parent / "conformal_calibrate.py")
cc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cc)


def test_small_n_honest_emptiness():
    # n < n_min ⇒ garantie None, jamais fabriquée
    r = cc.conformal_tau(np.array([0.9, 0.8]), np.array([False, False]), 0.10, n_min=12)
    assert r["tau"] is None and r["guarantee"] is None
    assert "insufficient data" in r["reason"]


def test_perfect_classifier_keeps_all_within_guarantee():
    conf = np.linspace(0.1, 0.9, 50)
    errors = np.zeros(50, dtype=bool)  # aucune erreur
    r = cc.conformal_tau(conf, errors, 0.10, n_min=12)
    assert r["kept"] == 50 and r["err_kept"] == 0
    assert r["realized_err_rate"] == 0.0
    assert r["coverage_share"] == 1.0


def test_all_errors_forces_full_abstention():
    conf = np.linspace(0.1, 0.9, 30)
    errors = np.ones(30, dtype=bool)  # tout faux ⇒ aucune ligne ne satisfait err≤α
    r = cc.conformal_tau(conf, errors, 0.10, n_min=12)
    assert r["tau"] == float("inf") and r["kept"] == 0


def test_threshold_respects_alpha_on_noisy_data():
    rng = np.random.default_rng(0)
    n = 400
    conf = rng.uniform(0, 1, n)
    # erreur anti-corrélée à conf : les peu confiants se trompent
    errors = rng.uniform(0, 1, n) > (conf * 0.95)
    for alpha in (0.05, 0.10):
        r = cc.conformal_tau(conf, errors, alpha, n_min=12)
        if r["realized_err_rate"] is not None:
            assert r["realized_err_rate"] <= alpha + 1e-9  # invariant dur
            assert r["tau"] <= float(conf.max())


def test_wilson_bounds_are_valid_and_ordered():
    rng = np.random.default_rng(1)
    conf = rng.uniform(0, 1, 100)
    errors = rng.uniform(0, 1, 100) > conf
    r = cc.conformal_tau(conf, errors, 0.10, n_min=12)
    if r["wilson95"]:
        lo, hi = r["wilson95"]
        assert 0.0 <= lo <= hi <= 1.0


def test_registered_alphas_are_sorted_grid_no_posthoc():
    # la grille est pré-enregistrée, croissante — pas étendue après lecture
    assert tuple(cc.ALPHAS) == (0.05, 0.10)
    assert cc.N_MIN == 12
