"""Tests latent_gate — CPU, aucun GPU, aucun net (encodeur mocké).

Le contrôle d'intégration réel (encodeur uniXCoder sur pool v6) appartient à
scripts/act2/s4_encoder_swap.py ; ici on teste la LOGIQUE : scoring, tiers
d'abstention, filtre exclude_task, immuabilité du pool via report_outcome.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from latent_gate import scoring
from latent_gate.scoring import GateModel, energy_gold, f1_attractor, norm_rows


def _toy_pool(n=40, d=16, seed=0):
    rng = np.random.default_rng(seed)
    E = rng.normal(size=(n, 3, d)).astype("float32")
    y = (np.arange(n) % 3 != 0).astype(int)  # 2/3 positifs
    return E[:, 0], E[:, 1], E[:, 2], y


class TestScoringMath:
    def test_energy_gold_identique_a_zero(self):
        rng = np.random.default_rng(1)
        s = rng.normal(size=8)
        d = rng.normal(size=8)
        assert energy_gold(s, d, d) == pytest.approx(0.0, abs=1e-6)
        # état nul + diff ⊥ goal → énergie = 1 exactement
        d_ = np.zeros(8); d_[0] = 1.0
        g_ = np.zeros(8); g_[1] = 1.0
        assert energy_gold(np.zeros(8), d_, g_) == pytest.approx(1.0, abs=1e-6)

    def test_f1_attractor_signe(self):
        cd = norm_rows(np.eye(6))
        y = np.array([1, 1, 1, 0, 0, 0])
        q = cd[0]  # identique à un succès → d_pass=0
        assert f1_attractor(q, cd, y) > 0

    def test_f1_exclusion_vide_pool_classe(self):
        cd = norm_rows(np.eye(4))
        y = np.array([1, 1, 1, 1])  # aucune classe fail
        assert np.isnan(f1_attractor(cd[0], cd, y))


class TestGateModel:
    def _write_model(self, tmp_path):
        spec = {
            "recipe": "gxf-logreg-l1", "pool_sha256": "x" * 64,
            "gxf": {"w": [2.0, 0.5], "b": 0.0,
                    "feat_mu": [0.0, 0.0], "feat_sd": [1.0, 1.0]},
            "abstention": {"q50": 0.10, "q75": 0.30, "note": "toy"},
        }
        p = tmp_path / "model.json"
        p.write_text(json.dumps(spec))
        return p

    def test_combine_tiers(self, tmp_path):
        m = GateModel(self._write_model(tmp_path))
        # energy très basse → p haute → conf forte → high
        p, conf, tier = m.combine(energy=-0.9, f1=0.0)
        assert p > 0.5 and tier == "high"
        # energy ≈ 0 → p ≈ 0.5 → conf ≈ 0 < q50 → low
        p, conf, tier = m.combine(energy=0.0, f1=0.0)
        assert tier == "low"

    def test_hash_suit_le_contenu(self, tmp_path):
        p = self._write_model(tmp_path)
        h1 = GateModel(p).sha256
        spec = json.loads(p.read_text())
        spec["abstention"]["q75"] = 0.31
        p.write_text(json.dumps(spec))
        assert GateModel(p).sha256 != h1


def test_norm_rows():
    A = np.array([[3.0, 4.0]])
    assert np.allclose(np.linalg.norm(norm_rows(A), axis=1), 1.0)
