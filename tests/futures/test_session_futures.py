"""Ghost pivot 15.1/15.2 — tests déterministes (zéro ssh, zéro appel)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def sb():
    return _load("sb", ROOT / "scripts" / "futures" / "session_bootstrap.py")


@pytest.fixture()
def lc():
    return _load("lc", ROOT / "scripts" / "futures" / "local_calibration.py")


def test_select_informative_deterministe(sb):
    cands = [{"id": f"c{i}"} for i in range(11)]
    scores = {f"c{i}": float(i) - 5.0 for i in range(11)}
    a = [c["id"] for c in sb.select_informative(cands, 3, scores)]
    b = [c["id"] for c in sb.select_informative(cands, 3, scores)]
    assert a == b
    assert len(a) == 3 and len(set(a)) == 3
    assert "c5" in a


def test_select_informative_sans_prior(sb):
    cands = [{"id": f"c{i}"} for i in range(5)]
    sel = sb.select_informative(cands, 5, None)
    assert [c["id"] for c in sel] == [f"c{i}" for i in range(5)]


def test_conformalize_insufficient(lc):
    out = lc.conformalize(np.array([0.1, 0.2]), np.array([0.5, 0.5]), 0.10)
    assert out["regime"] == "insufficient"


def test_conformalize_local_shape(lc):
    rng = np.random.default_rng(7)
    err = rng.random(20)
    out = lc.conformalize(rng.random(20), err, 0.10)
    assert out["regime"] == "local" and 0.0 <= out["tau"] <= 1.0
    assert out["n"] == 20


def test_session_scores_shape(lc):
    rng = np.random.default_rng(3)
    Ep = rng.normal(size=(30, 16)).astype(np.float32)
    Ep /= np.linalg.norm(Ep, axis=1, keepdims=True)
    yp = np.array([1] * 20 + [0] * 10)
    Ec = rng.normal(size=(5, 16)).astype(np.float32)
    Ec /= np.linalg.norm(Ec, axis=1, keepdims=True)
    sc = lc.session_scores(np.zeros((0, 16), dtype=np.float32), np.zeros(0, dtype=int), Ep, yp, Ec)
    assert sc.shape == (5,)
    assert np.isfinite(sc).all()
