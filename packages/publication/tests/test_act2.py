"""Act II publication assembly (story 6.4): chained, branch-explicit, gated."""

from __future__ import annotations

import json

import pytest
from core_schema.errors import SchemaError
from publication.act2 import (
    assemble_act2_release,
    select_preprint_template,
    sm3_evaluation,
)

A164 = "a" * 64


def _inputs(tmp_path, *, met=True, within=True):
    delta = {"claim_line": {"erbve_delta_pp": 25.1 if met else 1.2},
             "oq4": {"met": met, "verdict": "material-reduction" if met else "below-threshold",
                     "minimum_publishable_pp": 5.0}}
    rerun = {"within_tolerance": within, "rerun": {"operator": "R2E-Lab", "affiliation": "independent"}}
    pins = {"campaign": "act2-intervention"}
    d, r, p = tmp_path / "delta.json", tmp_path / "rerun.json", tmp_path / "pins.json"
    d.write_text(json.dumps(delta)); r.write_text(json.dumps(rerun)); p.write_text(json.dumps(pins))
    return d, r, p


def test_branch_selection_mechanical():
    assert select_preprint_template(True) == "material-reduction.md"
    assert select_preprint_template(False) == "below-threshold.md"


def test_sm3_records_against_the_release():
    ok = sm3_evaluation({"published_delta_pp": 25.1, "minimum_pp": 5.0}, {"within_tolerance": True})
    assert ok["outcome"] == "met"
    ko = sm3_evaluation({"published_delta_pp": 1.2, "minimum_pp": 5.0}, {"within_tolerance": True})
    assert ko["outcome"].startswith("not met")
    assert ko["measured"]["delta_pp"] == 1.2  # recorded, not hidden


def test_assembly_act2_packet(tmp_path):
    d, r, p = _inputs(tmp_path)
    out = assemble_act2_release(tmp_path / "pkt", delta_json=d, rerun_report_json=r,
                                verdict_text="# verdict\nreal text",
                                campaign_pins_json=p, act1_release_hash=A164, code_commit="c" * 40)
    assert out["references_act1_release"] == A164
    assert out["preprint_branch"]["template"] == "material-reduction.md"
    assert out["sm3"]["outcome"] == "met"
    pkt = tmp_path / "pkt"
    assert (pkt / "release-manifest-block.json").is_file()
    assert "Zenodo" in out["distribution_note"] and "pending" in out["distribution_note"]


def test_below_threshold_publishes_exactly_that(tmp_path):
    d, r, p = _inputs(tmp_path, met=False)
    out = assemble_act2_release(tmp_path / "pkt", delta_json=d, rerun_report_json=r,
                                verdict_text="below-threshold statement",
                                campaign_pins_json=p, act1_release_hash=A164, code_commit="c" * 40)
    assert out["preprint_branch"]["template"] == "below-threshold.md"
    assert out["sm3"]["outcome"].startswith("not met")


def test_guards(tmp_path):
    d, r, p = _inputs(tmp_path)
    with pytest.raises(SchemaError):  # bad act1 hash
        assemble_act2_release(tmp_path / "a", delta_json=d, rerun_report_json=r,
                              verdict_text="ok", campaign_pins_json=p,
                              act1_release_hash="not-a-hash", code_commit="c" * 40)
    with pytest.raises(SchemaError):  # unrendered placeholders
        assemble_act2_release(tmp_path / "b", delta_json=d, rerun_report_json=r,
                              verdict_text="delta {delta} pp", campaign_pins_json=p,
                              act1_release_hash=A164, code_commit="c" * 40)
    with pytest.raises(SchemaError):  # missing rerun report (FR-10)
        assemble_act2_release(tmp_path / "c", delta_json=d,
                              rerun_report_json=tmp_path / "nope.json",
                              verdict_text="ok", campaign_pins_json=p,
                              act1_release_hash=A164, code_commit="c" * 40)
