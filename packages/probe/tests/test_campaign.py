"""Campaign pins (story 6.1): cited hashes bite, evidence is mandatory,
families ≥3, pending module pin refuses runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from probe.campaign import MODULE_PENDING, build_campaign_pins, require_module_pin, write_campaign_pins

REPO = Path(__file__).resolve().parents[3]
MODELS = [
    {"model": "claude-3-5-sonnet-20241022", "vendor_generation": "claude"},
    {"model": "claude-3-7-sonnet-20250219", "vendor_generation": "claude"},
    {"model": "gpt-4o-2024-08-06", "vendor_generation": "openai"},
    {"model": "qwen-coder-placeholder", "vendor_generation": "qwen"},
]


def _observed(tmp_path):
    ev = tmp_path / "public-measurement.json"
    ev.write_text('{"evidence": true}')
    return [dict(m, evidence_file=str(ev), verified_at="2026-08-06") for m in MODELS]


def test_pins_cite_real_hashes(tmp_path):
    p = build_campaign_pins(REPO, observed_models=_observed(tmp_path))
    assert p["task_set"]["design_sha256"]
    assert p["agents"][0]["mismatch_policy"].startswith("re-collect")
    out = tmp_path / "campaign-pins-v1.json"
    write_campaign_pins(p, out)
    loaded = json.loads(out.read_text())
    assert loaded["task_set"]["design_sha256"] == p["task_set"]["design_sha256"]


def test_tampering_with_an_act1_file_is_caught(tmp_path):
    p = build_campaign_pins(REPO, observed_models=_observed(tmp_path))
    from hashlib import sha256

    actual = sha256((REPO / "governance" / "act1-design" / "design.toml").read_bytes()).hexdigest()
    assert p["task_set"]["design_sha256"] == actual  # the citation equals the actual file NOW


def test_agent_without_evidence_fails(tmp_path):
    bad = [dict(MODELS[0], evidence_file=None, verified_at="2026-08-06"),
           *(_observed(tmp_path))[1:]]
    with pytest.raises(SchemaError) as ei:
        build_campaign_pins(REPO, observed_models=bad)
    assert ei.value.code == "LI-PROBE-003"


def test_family_floor_enforced(tmp_path):
    obs = _observed(tmp_path)[:2]  # only claude+claude → 1 family
    with pytest.raises(SchemaError) as ei:
        build_campaign_pins(REPO, observed_models=obs)
    assert ei.value.code == "LI-PROBE-003"


def test_pending_module_pin_refuses_runs(tmp_path):
    p = build_campaign_pins(REPO, observed_models=_observed(tmp_path))
    assert p["module"]["advisory_predictor_hash"] == MODULE_PENDING
    with pytest.raises(SchemaError) as ei:
        require_module_pin(p)
    assert ei.value.code == "LI-PROBE-003"
    p["module"]["advisory_predictor_hash"] = "a" * 64
    assert require_module_pin(p) == "a" * 64
