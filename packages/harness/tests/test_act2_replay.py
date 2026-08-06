"""Act II replay tiers (story 6.3): bitwise Tier-1, declared re-run, routing."""

from __future__ import annotations

from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from harness.act2_replay import assemble_delta_bundle, rerun_report, verify_delta_bundle

REPO = Path(__file__).resolve().parents[3]
DECISION = REPO / "governance" / "probe-design" / "decision.toml"
DESIGN = REPO / "governance" / "act1-design" / "design.toml"

A1 = [{"family": "claude", "generation": "2025", "macro_rate": 0.651,
       "total_attempts": 2739, "n_tasks": 2336}]
A2 = [{"family": "claude", "generation": "2025", "macro_rate": 0.40,
       "total_attempts": 2000, "n_tasks": 2336}]
DELTA = (0.651 - 0.40) * 100.0  # 25.1 pp


def _bundle(tmp_path):
    return assemble_delta_bundle(tmp_path, act1_points=A1, act2_points=A2,
                                 decision_toml=DECISION, design_toml=DESIGN)


def test_tier1_bitwise_recompute(tmp_path):
    b = _bundle(tmp_path)
    v = verify_delta_bundle(b)
    assert abs(v["claim_erbve_delta_pp"] - DELTA) < 1e-9
    assert v["met"] is True
    assert len(v["output_sha256"]) == 64
    # re-verify: fresh out dir each time → deterministic bytes
    v2 = verify_delta_bundle(b)
    assert v2["output_sha256"] == v["output_sha256"]


def test_declared_independent_rerun_within_tolerance(tmp_path):
    b = _bundle(tmp_path)
    r = rerun_report(b, published_delta_pp=DELTA + 0.01, operator="R2E-Lab",
                     affiliation="independent (no shared affiliation with the builder)",
                     tolerance_pp=2.0)
    assert r["within_tolerance"] is True and r["divergence_route"] is None
    assert r["rerun"]["affiliation"].startswith("independent")


def test_divergence_routes_to_erratum_never_patches(tmp_path):
    b = _bundle(tmp_path)
    r = rerun_report(b, published_delta_pp=DELTA + 3.0,  # 3.01pp off, tolerance 2.0
                     operator="X", affiliation="declared", tolerance_pp=2.0)
    assert r["within_tolerance"] is False
    assert r["divergence_route"] == "governance/erratum-protocol.md"


def test_tolerance_boundary_inclusive(tmp_path):
    b = _bundle(tmp_path)
    r = rerun_report(b, published_delta_pp=DELTA + 0.02, operator="X",
                     affiliation="declared", tolerance_pp=2.0)
    assert r["within_tolerance"] is True  # exactly 2.00pp is INCLUSIVE per the sealed design


def test_bundle_refuses_empty_and_existing(tmp_path):
    with pytest.raises(SchemaError):
        assemble_delta_bundle(tmp_path, act1_points=[], act2_points=A2,
                              decision_toml=DECISION, design_toml=DESIGN)
    b = _bundle(tmp_path)
    assert b.exists()
    with pytest.raises(SchemaError):
        _bundle(tmp_path)  # same path → new version required


def test_rerun_requires_declarations(tmp_path):
    b = _bundle(tmp_path)
    with pytest.raises(SchemaError):
        rerun_report(b, published_delta_pp=DELTA, operator="", affiliation="declared",
                     tolerance_pp=2.0)
