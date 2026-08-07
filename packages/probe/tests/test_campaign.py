"""Campaign pins (story 6.1): cited hashes bite, evidence is mandatory and
repo-contained, families floor from the SEALED file, pending slots refuse."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from probe.campaign import (
    _SHA_RE,
    build_campaign_pins,
    require_module_pin,
    require_task_set,
    write_campaign_pins,
)

REPO = Path(__file__).resolve().parents[3]
MODELS = [
    {"model": "claude-3-5-sonnet-20241022", "vendor_generation": "claude"},
    {"model": "claude-3-7-sonnet-20250219", "vendor_generation": "claude"},
    {"model": "gpt-4o-2024-08-06", "vendor_generation": "openai"},
    {"model": "qwen-coder-32b", "vendor_generation": "qwen"},
]
EVIDENCE_REL = "governance/public-measurement-2026-08-06.json"


def _observed():
    return [dict(m, evidence_file=EVIDENCE_REL, verified_at="2026-08-06") for m in MODELS]


def test_floor_value_comes_from_the_sealed_file():
    """The number 3 must not be a Python constant — read tasks.toml [subset]."""
    import tomllib

    sealed = tomllib.loads((REPO / "governance" / "act1-design" / "tasks.toml").read_text())
    assert sealed["subset"]["families_required"] == 3  # the sealed value
    p = build_campaign_pins(REPO, observed_models=_observed())
    assert len(p["agents"]) == 4


def test_two_families_fail_closed_live_posture():
    obs = _observed()[:3]  # claude×2 + openai — the ACTUAL Act I posture
    with pytest.raises(SchemaError) as ei:
        build_campaign_pins(REPO, observed_models=obs)
    assert ei.value.code == "LI-PROBE-003"


def test_agent_validation_is_strict(tmp_path):
    for bad_field, val in [("evidence_file", ""), ("verified_at", None),
                           ("verified_at", "yesterday"), ("vendor_generation", "")]:
        obs = _observed()
        obs[0] = {**obs[0], bad_field: val}
        with pytest.raises(SchemaError):
            build_campaign_pins(REPO, observed_models=obs)


def test_evidence_outside_repo_refused():
    obs = _observed()
    obs[0] = {**obs[0], "evidence_file": "../../etc/passwd"}
    with pytest.raises(SchemaError):
        build_campaign_pins(REPO, observed_models=obs)


def test_same_bytes_parse_and_hash_cited():
    p = build_campaign_pins(REPO, observed_models=_observed())
    actual = sha256((REPO / "governance" / "act1-design" / "design.toml").read_bytes()).hexdigest()
    assert p["design"]["sha256"] == actual
    assert p["protocol"]["sha256"] == sha256(
        (REPO / "governance" / "probe-design" / "decision.toml").read_bytes()).hexdigest()
    assert p["inputs"]["corpus_version"] == "corpus-v0"  # AD-13 leg
    assert p["task_set"]["status"] == "frozen"  # gelée le 2026-08-07 (fenêtre d'exécution)
    assert p["task_set"]["n"] == 32  # le manchon pilote, seed 6769
    assert p["harness"]["name"] == "harbor + our trace wrapper"


def test_module_and_task_slots_stateful_not_lying():
    p = build_campaign_pins(REPO, observed_models=_observed())
    h = p["module"]["advisory_predictor_hash"]
    gov = json.loads((REPO / "governance" / "act2" / "campaign-pins-v1.json").read_text())
    gov_h = gov["module"]["advisory_predictor_hash"]
    # builder must emit EXACTLY what gouvernance enregistre — pas deux vérités
    assert h == gov_h
    if _SHA_RE.fullmatch(h):
        require_module_pin(p)  # pin réel enregistré ce matin → passe
    else:
        with pytest.raises(SchemaError):
            require_module_pin(p)
    # garbage hex is never a pin
    p["module"]["advisory_predictor_hash"] = "z" * 64
    with pytest.raises(SchemaError):
        require_module_pin(p)
    p["module"]["advisory_predictor_hash"] = "a" * 64
    assert require_module_pin(p) == "a" * 64
    p["task_set"] = {"status": "frozen", "n": 481, "file": "…", "sha256": "b" * 64}
    assert require_module_pin(p) == "a" * 64
    assert require_task_set(p)["n"] == 481


def test_write_and_reload_roundtrip(tmp_path):
    p = build_campaign_pins(REPO, observed_models=_observed())
    out = tmp_path / "campaign-pins-v1.json"
    write_campaign_pins(p, out)
    assert json.loads(out.read_text()) == p
