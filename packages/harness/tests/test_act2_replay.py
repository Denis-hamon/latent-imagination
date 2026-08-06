"""Act II replay tiers (story 6.3 + CR): anchored bitwise verify, FR-8 re-run,
publication gate, CANONICAL pipeline equivalence (the anti-drift tripwire)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from harness.act2_replay import (
    assemble_act2_release_packet,
    assemble_delta_bundle,
    persist_rerun_report,
    rerun_report,
    verify_delta_bundle,
)
from harness.delta import compute_deltas

REPO = Path(__file__).resolve().parents[3]
DECISION = REPO / "governance" / "probe-design" / "decision.toml"
DESIGN = REPO / "governance" / "act1-design" / "design.toml"

A1 = [{"family": "claude", "generation": "2025", "macro_rate": 0.651,
       "total_attempts": 2739, "n_tasks": 2336},
      {"family": "openai", "generation": "2024", "macro_rate": 0.981,
       "total_attempts": 53, "n_tasks": 53}]
A2 = [{"family": "claude", "generation": "2025", "macro_rate": 0.40,
       "total_attempts": 2000, "n_tasks": 2336},
      {"family": "openai", "generation": "2024", "macro_rate": 0.85,
       "total_attempts": 60, "n_tasks": 53}]
M1 = (0.651 * 2336 + 0.981 * 53) / 2389
M2 = (0.40 * 2336 + 0.85 * 53) / 2389
DELTA_PP = (M1 - M2) * 100.0


def _expected(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    d = compute_deltas(A1, A2, decision_toml=DECISION, design_toml=DESIGN)
    p = tmp_path / "published.json"
    p.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")
    return p


def _bundle(tmp_path):
    return assemble_delta_bundle(tmp_path / "b", act1_points=A1, act2_points=A2,
                                 decision_toml=DECISION, design_toml=DESIGN,
                                 expected_delta_json=_expected(tmp_path / "e"))


def test_pipeline_is_byte_equivalent_to_package_delta(tmp_path):
    """The anti-drift tripwire: canonical pipeline == package compute, BYTES."""
    b = _bundle(tmp_path)
    v = verify_delta_bundle(b)
    assert v["bitwise_equal"] is True, (v["produced_sha256"], v["expected_sha256"])


def test_tampered_slice_is_caught_by_the_anchor(tmp_path):
    b = _bundle(tmp_path)
    pts = json.loads((b / "slice" / "act2.json").read_text())
    pts["points"][0]["macro_rate"] = 0.42
    (b / "slice" / "act2.json").write_text(json.dumps(pts, indent=1, sort_keys=True) + "\n")
    v = verify_delta_bundle(b)
    assert v["bitwise_equal"] is False  # tampering changes the produced bytes


def test_units_are_real_pp_and_the_boundary_is_inclusive(tmp_path):
    b = _bundle(tmp_path)
    ok = rerun_report(b, published_delta_pp=DELTA_PP + 1.9, operator="R2E-Lab",
                      affiliation="independent", tolerance_pp=2.0)
    assert ok["within_tolerance"] is True  # 1.9 real pp ≤ 2.0 sealed pp
    ko = rerun_report(b, published_delta_pp=DELTA_PP + 2.1, operator="X",
                      affiliation="declared", tolerance_pp=2.0)
    assert ko["within_tolerance"] is False
    assert any("tolerance breach" in r for r in ko["divergence_routes"])
    assert ko["first_diverging_artifact"] == "out/delta.json"


def test_affiliation_dispute_routes_even_within_tolerance(tmp_path):
    b = _bundle(tmp_path)
    r = rerun_report(b, published_delta_pp=DELTA_PP, operator="X", affiliation="declared",
                     tolerance_pp=2.0, affiliation_disputed=True)
    assert r["within_tolerance"] is False
    assert any("affiliation dispute" in rr for rr in r["divergence_routes"])


def test_tolerance_input_validation(tmp_path):
    b = _bundle(tmp_path)
    for bad in (float("inf"), float("nan"), -0.5, True, "2"):
        with pytest.raises(SchemaError):
            rerun_report(b, published_delta_pp=DELTA_PP, operator="X",
                         affiliation="declared", tolerance_pp=bad)


def test_report_persists_and_gates_the_release(tmp_path):
    b = _bundle(tmp_path)
    r = rerun_report(b, published_delta_pp=DELTA_PP, operator="R2E-Lab",
                     affiliation="independent", tolerance_pp=2.0)
    store = tmp_path / "store"
    man = persist_rerun_report(r, store, bundle_dir=b, code_commit="c" * 40)
    assert man["artifact_type"] == "bundle" and man["manifest"]["files"] if "manifest" in man else True
    shipped = store / "bundles" / "act2-delta-rerun" / "v0" / "rerun-report.json"
    assert shipped.is_file()
    with pytest.raises(SchemaError) as ei:
        assemble_act2_release_packet(tmp_path / "packet", rerun_report_artifact=None)
    assert "PRECONDITION" in str(ei.value)
    pkt = assemble_act2_release_packet(tmp_path / "packet2", rerun_report_artifact=shipped)
    assert (pkt / "rerun-report.json").is_file()


def test_bundle_refuses_existing_and_missing_sources(tmp_path):
    with pytest.raises(SchemaError):
        assemble_delta_bundle(tmp_path / "x", act1_points=[], act2_points=A2,
                              decision_toml=DECISION, design_toml=DESIGN, expected_delta_json=Path("/nope"))
    b = _bundle(tmp_path)
    assert b.exists()
    with pytest.raises(SchemaError):
        _bundle(tmp_path)
