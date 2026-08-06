"""Latency bench (story 5.4): percentile math, budget loading, miss posture."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from gate.bench import bench_report, load_budget, percentile, verdict
from gate.intercept import CandidateCtx
from gate.serve import GateServer

D = Path(__file__).resolve().parents[3]
BUDGET = D / "governance" / "gate" / "latency-budget-v1.toml"


def test_percentile_math():
    xs = sorted(range(100))  # 0..99 — nearest-rank: P_q = xs[ceil(q/100*N)-1]
    assert percentile(xs, 50) == 49
    assert percentile(xs, 95) == 94
    assert percentile(xs, 99) == 98
    assert percentile([1.0], 95) == 1.0
    with pytest.raises(SchemaError):
        percentile([], 95)
    with pytest.raises(SchemaError):
        percentile([2.0, 1.0], 50)  # unsorted input refused


def test_budget_load_and_errors(tmp_path):
    assert load_budget(BUDGET) == 1.0
    with pytest.raises(SchemaError) as ei:
        load_budget(tmp_path / "nope.toml")
    assert ei.value.code == "LI-GATE-007"
    bad = tmp_path / "bad.toml"
    bad.write_text("[budget]\np95_seconds = -1\n")
    with pytest.raises(SchemaError):
        load_budget(bad)


def _server(tmp_path):
    art = {
        "predictor_version": "probe-predictor-v0", "corpus_version": "corpus-v0",
        "measured": {"precision": 0.6271},
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "n_features": 2**12,
                       "alternate_sign": False, "norm": "l2", "lowercase": True,
                       "token_pattern": r"\b\w\w+\b"},
        "model": {"kind": "logreg-sigmoid", "intercept": 0.5, "coefficients": [0.0] * 2**12},
    }
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "META.json").write_text(json.dumps({"layout_version": "store-layout-v1",
                                                "store_version": "a" * 64}))
    (snap / "predictor.json").write_text(json.dumps(art, allow_nan=False))
    return GateServer.load(snap, expected_predictor_hash=sha256(json.dumps(art).encode()).hexdigest(),
                           log_path=tmp_path / "dep" / "decisions.jsonl")


def test_bench_report_shape_and_cold_warm_split(tmp_path):
    server = _server(tmp_path)
    docs = [f"# PATCH DIFF\n+ fix line {i}\n# FAILED TESTS\ntests/test_bench.py::t" for i in range(6)]
    rep = bench_report(server, docs, lambda d: CandidateCtx(repo="o/r", patch_diff=d,
                       rationale_ptr="x"), hardware_note="test-host")
    assert rep["cold"]["n"] == 6
    assert rep["warm"]["n"] >= 6
    assert rep["warm"]["p95_s"] >= rep["warm"]["p50_s"]
    assert rep["corpus_version"] == "corpus-v0"
    assert rep["predictor_hash"] == server.snapshot.predictor_hash


def test_verdict_meet_and_miss():
    rep_ok = {"warm": {"p95_s": 0.5}}
    assert verdict(rep_ok, 1.0)["verdict"] == "meets-budget"
    rep_miss = {"warm": {"p95_s": 2.0}}
    v = verdict(rep_miss, 1.0)
    assert v["verdict"] == "annotations-async"
    assert "do NOT quote" in v["guidance"]  # SM-C3: never a claim beyond measurement
