"""Act II publication assembly (story 6.4 + CR): cross-bound chain, SM-3 on
the third-party number, atomic packet, rendered verdict."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from harness.delta import (  # noqa: F401 (render used via act2)
    compute_deltas,
    render_verdict,
)
from publication.act2 import assemble_act2_release, sm3_evaluation

REPO = Path(__file__).resolve().parents[3]
TEMPLATES = REPO / "governance" / "act2" / "verdict-templates"
DECISION = REPO / "governance" / "probe-design" / "decision.toml"
DESIGN = REPO / "governance" / "act1-design" / "design.toml"
A164, CC = "a" * 64, "c" * 64


def _delta_dict(met=True, pp=25.1):
    cl = _act(pp)
    return {"claim_line": cl,
            "per_series": [],
            "tolerance_pp": 2.0,
            "_citations": {"decision_toml_sha256": "e" * 64, "design_toml_sha256": "f" * 64},
            "oq4": {"met": met, "verdict": "material-reduction" if met else "below-threshold",
                    "minimum_publishable_pp": 5.0}}


def _act(pp):
    return {"erbve_delta_pp": pp, "exec_per_task_delta": -0.2, "time_to_valid_delta_s": None,
            "ttv_coverage": "0/2", "aggregation": "pooled macro-per-task, Act I discipline (never a mean of family means)",
            "delta_ci": None, "ci_status": "fixture"}


def _write_pair(tmp_path, *, met=True, pp=25.1, anchor=True):
    delta = _delta_dict(met=met, pp=pp)
    delta_bytes = (json.dumps(delta, indent=1, sort_keys=True) + "\n").encode()
    d = tmp_path / "delta.json"
    d.write_bytes(delta_bytes)
    rerun = {
        "rerun": {"operator": "R2E-Lab", "affiliation": "independent"},
        "published_delta_pp": pp, "reproduced_delta_pp": pp - 0.01,
        "within_tolerance": True,
        "bitwise_anchor": {"expected_sha256": sha256(delta_bytes).hexdigest() if anchor else "b" * 64,
                            "bitwise_equal": anchor},
    }
    r = tmp_path / "rerun.json"
    r.write_text(json.dumps(rerun))
    pins = tmp_path / "pins.json"
    pins.write_text('{"campaign": "act2-intervention"}')
    return d, r, pins


def test_assembly_full_chain_bound(tmp_path):
    d, r, p = _write_pair(tmp_path)
    out = assemble_act2_release(tmp_path / "pkt", delta_json=d, rerun_report_json=r,
                                templates_dir=TEMPLATES, campaign_pins_json=p,
                                act1_release_hash=A164, code_commit=CC)
    assert out["references_act1_release_hash"] == A164
    assert out["preprint_branch"]["template"] == "material-reduction.md"
    assert out["preprint_branch"]["template_sha256"]
    assert out["sm3"]["outcome"] == "met"
    assert out["sm3"]["measured"]["reproduced_delta_pp"] == pytest.approx(25.09)
    pkt = tmp_path / "pkt"
    block = json.loads((pkt / "release-manifest-block.json").read_text())
    assert block["contents"]["verdict_md_sha256"]
    # the packet's verdict is the TEMPLATE RENDER — guaranteed by construction
    assert "NOT met" not in (pkt / "verdict.md").read_text()


def test_cross_binding_rerun_must_anchor_this_delta(tmp_path):
    d, r, p = _write_pair(tmp_path, anchor=False)  # rerun anchors other bytes
    with pytest.raises(SchemaError) as ei:
        assemble_act2_release(tmp_path / "pkt", delta_json=d, rerun_report_json=r,
                              templates_dir=TEMPLATES, campaign_pins_json=p,
                              act1_release_hash=A164, code_commit=CC)
    assert "DIFFERENT delta figure" in str(ei.value)


def test_sm3_is_the_third_party_number():
    r = {"published_delta_pp": 6.9, "reproduced_delta_pp": 4.9,
         "within_tolerance": True, "bitwise_anchor": {"bitwise_equal": True}}
    out = sm3_evaluation(r, minimum_pp=5.0)
    assert out["outcome"].startswith("not met")  # 4.9 < 5.0: written as "met" NO MORE


def test_strict_types_on_bools(tmp_path):
    d, r, p = _write_pair(tmp_path)
    rerun = json.loads(r.read_text())
    rerun["within_tolerance"] = "false"  # string poison — was bool("false")==True before
    r.write_text(json.dumps(rerun))
    with pytest.raises(SchemaError):
        assemble_act2_release(tmp_path / "pkt", delta_json=d, rerun_report_json=r,
                              templates_dir=TEMPLATES, campaign_pins_json=p,
                              act1_release_hash=A164, code_commit=CC)


def test_packet_refuses_nonempty_dir(tmp_path):
    d, r, p = _write_pair(tmp_path)
    assemble_act2_release(tmp_path / "pkt", delta_json=d, rerun_report_json=r,
                          templates_dir=TEMPLATES, campaign_pins_json=p,
                          act1_release_hash=A164, code_commit=CC)
    with pytest.raises(SchemaError) as ei:
        assemble_act2_release(tmp_path / "pkt", delta_json=d, rerun_report_json=r,
                              templates_dir=TEMPLATES, campaign_pins_json=p,
                              act1_release_hash=A164, code_commit=CC)
    assert "non-empty" in str(ei.value)


def test_delta_missing_claim_line_refused_before_writes(tmp_path):
    _d, r, p = _write_pair(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text('{"oq4": {"met": true, "verdict": "material-reduction", "minimum_publishable_pp": 5.0}}')
    with pytest.raises(SchemaError):
        assemble_act2_release(tmp_path / "pkt", delta_json=bad, rerun_report_json=r,
                              templates_dir=TEMPLATES, campaign_pins_json=p,
                              act1_release_hash=A164, code_commit=CC)
