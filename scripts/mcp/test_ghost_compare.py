"""Ghost v0.7.0 — compare_patches : règles produit mesurées en démo 15.4.

- Phase 1 (issues < 8) : plan d'exécution, AUCUNE recommandation.
- Phase 2 (issues >= 8) : calibration locale conforme, recommandation ;
  classe unique locale => abstention (jamais deviné).
Machinerie pure testée sans réseau ; intégration via embed monkeypatché
(pool v8 réel en fixture numpy, comme test_ghost_server_family).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
import ghost_server as gs

_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_test_cmp"] = s11
_spec.loader.exec_module(s11)
import ghost_compare as gc


def _separable_space(n_pos=12, n_neg=12, dim=32, seed=5):
    rng = np.random.default_rng(seed)
    center = np.ones(dim)
    Ep = center + rng.normal(scale=0.05, size=(n_pos, dim))
    En = -center + rng.normal(scale=0.05, size=(n_neg, dim))
    E = np.vstack([Ep, En]).astype(np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    y = np.array([1] * n_pos + [0] * n_neg)
    tasks = np.array([f"t{i}" for i in range(len(y))])
    return E, y, tasks


class TestMachineriePure:
    def test_informative_selection_deterministe(self):
        ids = [f"c{i}" for i in range(11)]
        scores = [float(i) - 5 for i in range(11)]
        a = gc.informative_selection(ids, scores, 3)
        b = gc.informative_selection(ids, scores, 3)
        assert a == b and len(a) == 3 and "c5" in a

    def test_selection_sature(self):
        assert gc.informative_selection(["a", "b"], [0.0, 1.0], 5) == ["a", "b"]

    def test_fallback_sous_n_min_ne_recommande_jamais(self):
        E, y, _ = _separable_space()
        Ec = E[:3]
        issues = {"c0": 1, "c1": 0}
        out = gc.calibrate_local(E, y, {"c0": E[0], "c1": E[1]}, issues,
                                 Ec, ["c0", "c1", "c2"], s11, n_min=8)
        assert out["regime"] == "fallback-prior"
        assert "recommendation" not in out
        assert "AUCUNE recommandation" in out["disclosure"]

    def test_calibration_locale_separe_et_recommande(self):
        E, y, _ = _separable_space()
        ids = [f"k{i}" for i in range(10)]
        Ex = np.vstack([E[0], E[1], E[2], E[12], E[13], E[14], E[3], E[15], E[4], E[16]]).astype(np.float32)
        issues = {ids[0]: 1, ids[1]: 1, ids[2]: 1, ids[3]: 0, ids[4]: 0,
                  ids[5]: 0, ids[6]: 1, ids[7]: 0}
        E_issues = {ids[i]: Ex[i] for i in range(8)}
        out = gc.calibrate_local(E, y, E_issues, issues, Ex, ids, s11, n_min=8)
        assert out["regime"] == "local"
        assert out["recommendation"] is not None
        assert out["recommendation"]["id"] in {ids[0], ids[1], ids[2], ids[6]}  # un positif mesuré
        for c in out["candidates"]:
            assert 0.0 <= c["p_success"] <= 1.0

    def test_fully_measured_K3_recommande_sans_n8(self):
        # leçon démo #9436 : K=3 tous mesurés => recommandation par mesure
        E, y, _ = _separable_space()
        ids = ["k0", "k1", "k2"]
        Ex = np.vstack([E[0], E[13], E[2]])
        issues = {"k0": 0, "k1": 1, "k2": 0}
        out = gc.calibrate_local(E, y, {i: Ex[ids.index(i)] for i in ids}, issues,
                                 Ex, ids, s11, n_min=8)
        assert out["regime"] == "fully-measured"
        assert out["recommendation"]["id"] == "k1"
        assert "mesurée" in out["recommendation"]["basis"]

    def test_fully_measured_tous_negatifs_abstention(self):
        E, y, _ = _separable_space()
        ids = ["k0", "k1"]
        Ex = np.vstack([E[13], E[14]])
        issues = {"k0": 0, "k1": 0}
        out = gc.calibrate_local(E, y, {i: Ex[ids.index(i)] for i in ids}, issues,
                                 Ex, ids, s11, n_min=8)
        assert out["regime"] == "fully-measured"
        assert out["recommendation"] is None

    def test_classe_unique_locale_abstention(self):
        E, y, _ = _separable_space()
        issues = {f"k{i}": 1 for i in range(9)}
        E_iss = {k: E[i % 6] for i, k in enumerate(issues)}
        out = gc.calibrate_local(E, y, E_iss, issues, E[:3], ["a", "b", "c"], s11, n_min=8)
        assert out["regime"] == "degenerate-local"
        assert "recommendation" not in out


class TestToolComparePatches:
    """Intégration : pool v8 réel, embed synthétique déterministe (pas de GPU)."""

    @pytest.fixture()
    def synth_embed(self, monkeypatch):
        def fake_embed(text):
            v = np.zeros(768, dtype=np.float32)
            rng = np.random.default_rng(abs(hash(text)) % (2**32))
            v = rng.normal(size=768).astype(np.float32)
            return v / (np.linalg.norm(v) + 1e-9)

        monkeypatch.setattr(gs, "embed", fake_embed)
        return fake_embed

    def _cands(self, k=5):
        return [{"id": f"c{i}", "state_text": f"probleme {i}",
                 "diff_text": f"diff --git a/f{i} b/f{i}\n+x{i}\n"} for i in range(k)]

    def test_phase1_plan_sans_recommandation(self, synth_embed):
        out = gs.do_compare_patches({"candidates": self._cands(5), "budget_n": 8})
        assert out["phase"] == "execution-plan"
        assert "recommendation" not in out
        assert len(out["execution_plan"]) >= 1
        assert "AUCUNE recommandation" in out["disclosure"]

    def test_phase2_avec_8_issues_reelles(self, synth_embed):
        cands = self._cands(12)
        issues = {f"c{i}": {"y": i % 2, "grounded_by": "pytest-f2p"} for i in range(8)}
        out = gs.do_compare_patches({"candidates": cands, "issues": issues, "budget_n": 8})
        assert out["phase"] in ("recommendation", "abstention")
        cal = out["calibration"]
        assert cal["n_local"] == 8
        if cal["regime"] == "local":
            assert all(set(c) >= {"p_success", "abstained"} for c in cal["candidates"])
            assert out["encoder"] == gs.ENCODER

    def test_issue_inconnue_rejetee(self, synth_embed):
        with pytest.raises(gs.ToolInputError):
            gs.do_compare_patches({"candidates": self._cands(2),
                                   "issues": {"ghost": {"y": 1}}})


class TestPerTestColumn:
    """DW-48 : colonne « tests prédits échoués » additive + abstention."""

    @pytest.fixture()
    def pertest_model(self, tmp_path, monkeypatch):
        rng = np.random.default_rng(42)
        w = rng.normal(size=1537).astype("float32")
        f = tmp_path / "pert-test-model.npz"
        np.savez(f, w=w, b=np.float32(0.1), threshold=np.float32(0.55), lam=np.float32(0.01))
        monkeypatch.setattr(gs, "PERTEST_PATH", f)
        monkeypatch.setattr(gs, "_PERTEST", None)
        return f

    @pytest.fixture()
    def synth_embed(self, monkeypatch):
        def fake_embed(text):
            rng = np.random.default_rng(abs(hash(text)) % (2**32))
            v = rng.normal(size=768).astype(np.float32)
            return v / (np.linalg.norm(v) + 1e-9)

        monkeypatch.setattr(gs, "embed", fake_embed)
        return fake_embed

    def _cands(self, k=3):
        return [{"id": f"c{i}", "state_text": f"probleme {i}",
                 "diff_text": f"diff --git a/f{i} b/f{i}\n+x{i}\n"} for i in range(k)]

    def test_unavailable_sans_fichier(self, synth_embed, tmp_path, monkeypatch):
        monkeypatch.setattr(gs, "PERTEST_PATH", tmp_path / "absent.npz")
        monkeypatch.setattr(gs, "_PERTEST", None)
        out = gs.do_compare_patches({"candidates": self._cands(),
                                     "declared_tests": ["t1"]})
        assert all(v["status"] == "unavailable"
                   for v in out["predicted_failing_tests"].values())

    def test_abstention_sans_tests_declares(self, synth_embed, pertest_model):
        out = gs.do_compare_patches({"candidates": self._cands()})
        col = out["predicted_failing_tests"]
        assert set(col) == {"c0", "c1", "c2"}
        assert all(v["status"] == "abstained" and v["tests"] == [] for v in col.values())
        assert all(v["reason"] == "no declared tests" for v in col.values())

    def test_mesure_ligne_par_test_avec_proba(self, synth_embed, pertest_model):
        out = gs.do_compare_patches({"candidates": self._cands(),
                                     "declared_tests": ["tests/a.ts > t1", "t2"]})
        v = out["predicted_failing_tests"]["c0"]
        assert v["status"] == "measured"
        assert len(v["tests"]) == 2
        for row in v["tests"]:
            assert 0.0 <= row["p_failing"] <= 1.0
            assert row["predicted_red"] == (row["p_failing"] >= v["model"]["threshold"])
        assert v["model"]["prereg"] == "3896a3e750a37f1d"
        assert v["model"]["threshold"] == pytest.approx(0.55, abs=1e-4)

    def test_colonne_additive_phase_inchangee(self, synth_embed, pertest_model):
        base = gs.do_compare_patches({"candidates": self._cands(5), "budget_n": 8})
        avec = gs.do_compare_patches({"candidates": self._cands(5), "budget_n": 8,
                                      "declared_tests": ["t1", "t2"]})
        assert base["phase"] == avec["phase"] == "execution-plan"
        assert base["execution_plan"] == avec["execution_plan"]
        assert "predicted_failing_tests" not in base or base is not avec
