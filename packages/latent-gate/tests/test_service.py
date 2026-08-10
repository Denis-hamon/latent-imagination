"""Tests service — logique de bout en bout avec encodeur mocké en fonction
déterministe (hash-seeded), modèle jouet, pool jouet. Zéro réseau, zéro GPU.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from latent_gate import service


def _fake_embed(text: str) -> np.ndarray:
    """Embedding déterministe 8-dim dérivé du hash du texte (aucun ML)."""
    import hashlib
    h = sha256 = hashlib.sha256(text.encode()).digest()
    v = np.frombuffer(h, dtype=np.uint8)[:8].astype(float)
    return (v - v.mean()) / (np.linalg.norm(v) + 1e-9)


class _ToyRows:
    pass


def _write_pool(tmp_path):
    rng = np.random.default_rng(7)
    n = 12
    rows = []
    for i in range(n):
        rows.append({"task": f"t{i % 4}", "arm": "on", "campaign": "toy",
                     "state": f"s{i}", "diff": f"d{i}", "gold": f"g{i}",
                     "y": int(i % 3 != 0)})
    z = rng.normal(size=(n, 3, 8)).astype("float32")
    (tmp_path / "latent-pool-v6.json").write_text(json.dumps(rows))
    np.savez(tmp_path / "latent-pool-v6.npz",
             E_state=z[:, 0], E_diff=z[:, 1], E_goal=z[:, 2])
    model = {"recipe": "gxf-logreg-l1", "pool_sha256": "0" * 64,
             "gxf": {"w": [1.5, 0.7], "b": 0.0,
                     "feat_mu": [0.0, 0.0], "feat_sd": [0.1, 0.1]},
             "abstention": {"q50": 0.08, "q75": 0.22, "note": "toy"}}
    mp = tmp_path / "model.json"
    mp.write_text(json.dumps(spec := model))
    return tmp_path, mp


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    pool_dir, mp = _write_model_and_pool = _write_pool(tmp_path)
    # pool_dir là où le service lit le pool
    monkeypatch.setenv("LI_POOL_DIR", str(pool_dir))
    monkeypatch.setenv("LI_POOL_NAME", "latent-pool-v6")
    monkeypatch.setenv("LI_MODEL_JSON", str(mp))
    monkeypatch.setenv("LI_OUTCOME_DIR", str(tmp_path / "outcomes"))
    # encodeur mocké
    monkeypatch.setattr(service.encoder, "embed_one", _fake_embed)
    # pool singleton reset
    import latent_gate.pool as poolmod
    poolmod._pool = None
    return tmp_path


class TestService:
    def test_score_patch_goalfree(self, wired):
        out = service.score_patch("état", "@@ diff", goal_text=None)
        assert out["advice"] == "goal-free-only"
        assert "attractor_score" in out

    def test_score_patch_goal_abstention_ou_pas(self, wired):
        out = service.score_patch("état", "@@ diff", goal_text="le but")
        assert out["advice"] in ("likely-pass", "likely-fail",
                                 "lean-pass", "lean-fail", "abstain")
        assert 0.0 <= out["p_pass"] <= 1.0
        assert out["confidence_tier"] in ("high", "mid", "low")

    def test_report_outcome_append_only(self, wired, tmp_path):
        service.report_outcome("abc", True)
        f = (tmp_path / "outcomes")
        files = list(f.glob("*.jsonl"))
        assert files, "outcome log manquant"
        content = files[0].read_text()
        assert "commit" not in content or "call_id" in content  # sha only
        entry = json.loads(content.strip().splitlines()[-1])
        assert entry["passed"] is True

    def test_health_hash_vitrine(self, wired):
        h = service.health()
        assert h["pool_n"] == 12
        assert h["recipe"] == "gxf-logreg-l1"


class TestNoMassageDuDiff:
    """Le diff arrive tel qu'émis : le service ne doit pas le toucher."""

    def test_pas_de_sanitize(self, wired, monkeypatch):
        seen = {}
        orig = service.encoder.embed_one

        def spy(t):
            seen.setdefault("texts", []).append(t)
            return orig(t)

        monkeypatch.setattr(service.encoder, "embed_one", spy)
        dirty = "@@ -1 +1 @@ garbage</diff> \n+pass\n<truncated>"
        service.score_patch("s", dirty, goal_text="g")
        assert any(t.startswith("@@ -1 +1 @@ garbage") for t in seen["texts"])
