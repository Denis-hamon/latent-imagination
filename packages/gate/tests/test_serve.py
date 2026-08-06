"""Wired serve path (story 5.2) + CI-coverable bit-compat (frozen truth vector
generated ON THE NODE with sklearn 1.9.0 — no ml extra needed in CI)."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from gate.intercept import CandidateCtx
from gate.predict import featurize
from gate.serve import GateServer

D = Path(__file__).resolve().parent
TRUTH = json.loads((D / "featurization-truth.json").read_text())

CTX = CandidateCtx(repo="o/r", patch_diff="diff --git a/x b/x\n+1\n",
                   rationale_ptr="governance/probe-design/model-strategy-v1.md")


def _artifact(parent):
    tmp_path = parent / "snap"  # snapshot hand-off IS a store root — keep logs outside it
    tmp_path.mkdir(parents=True, exist_ok=True)
    art = {
        "predictor_version": "probe-predictor-v0", "corpus_version": "corpus-v0",
        "measured": {"precision": 0.6271},
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "n_features": 2**12,
                       "alternate_sign": False, "norm": "l2", "lowercase": True,
                       "token_pattern": r"\b\w\w+\b"},
        "model": {"kind": "logreg-sigmoid", "intercept": 0.5, "coefficients": [0.0] * 2**12},
    }
    (tmp_path / "META.json").write_text(json.dumps(
        {"layout_version": "store-layout-v1", "store_version": "a" * 64}))
    (tmp_path / "predictor.json").write_text(json.dumps(art, allow_nan=False))
    return tmp_path, sha256(json.dumps(art, allow_nan=False).encode()).hexdigest()


def test_frozen_truth_vector_bitcompatible():
    """CI-hard: no sklearn needed — the truth was FROZEN from sklearn on the node."""
    for name, expected in TRUTH["columns"].items():
        got = featurize(TRUTH["docs"][name], TRUTH["n_features"])
        nz = {i: v for i, v in enumerate(got) if v != 0.0}
        assert nz.keys() == {int(k) for k in expected}, f"{name}: columns diverge"
        for col, v in nz.items():
            assert abs(v - expected[str(col)]) < 1e-7, f"{name} col {col}"


def test_serve_annotates_logs_and_times(tmp_path):
    root, phash = _artifact(tmp_path)
    log = tmp_path / "deployer" / "decisions.jsonl"
    server = GateServer.load(root, expected_predictor_hash=phash, log_path=log)
    ev = server.handle(CTX, prediction_target_tier="diff_touched", model_family="baseline")
    assert ev.kind == "gate_annotated"
    assert ev.payload["latency_s"] >= 0.0  # measured in the serve path
    assert ev.payload["predictor_disclosure"]["measured_precision"] == 0.6271
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1  # decision log IS the latency log (NFR-P1 path)


def test_serve_abstains_without_denominator(tmp_path):
    root, phash = _artifact(tmp_path)
    log = tmp_path / "deployer" / "decisions.jsonl"
    server = GateServer.load(root, expected_predictor_hash=phash, log_path=log)
    ev = server.handle(CTX, prediction_target_tier=None, model_family="baseline")
    assert ev.kind == "prediction_refused"
    assert "flip_probability" not in ev.payload


def test_serve_refuses_recipe_mismatch(tmp_path):
    root, _ = _artifact(tmp_path)
    art = json.loads((root / "predictor.json").read_text())
    art["vectorizer"]["norm"] = "l1"
    (root / "predictor.json").write_text(json.dumps(art))
    phash2 = sha256(json.dumps(art).encode()).hexdigest()
    with pytest.raises(SchemaError) as ei:
        GateServer.load(root, expected_predictor_hash=phash2, log_path=tmp_path / "d" / "decisions.jsonl")
    assert ei.value.code == "LI-GATE-006"


def test_serve_reports_latency_in_payload_even_on_stub_weights(tmp_path):
    root, phash = _artifact(tmp_path)
    server = GateServer.load(root, expected_predictor_hash=phash,
                             log_path=tmp_path / "deps" / "decisions.jsonl")
    ev = server.handle(CTX, prediction_target_tier="user_designated", model_family="b")
    assert "latency_s" in ev.payload
