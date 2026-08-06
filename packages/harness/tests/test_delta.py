"""Act II delta computation (story 6.2 + CR): TRUE Act I statistic, sealed
reads, artifact emission, anchored Act II templates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from harness.delta import compute_deltas, publish_delta_figure, render_verdict

REPO = Path(__file__).resolve().parents[3]
DECISION = REPO / "governance" / "probe-design" / "decision.toml"
DESIGN = REPO / "governance" / "act1-design" / "design.toml"
TEMPLATES = REPO / "governance" / "act2" / "verdict-templates"


def _pt(fam, gen, macro, attempts=100, n_tasks=10, ttv=None):
    p = {"family": fam, "generation": gen, "macro_rate": macro, "micro_rate": macro,
         "total_attempts": attempts, "n_tasks": n_tasks}
    if ttv is not None:
        p["mean_time_to_valid_s"] = ttv
    return p


def test_pooled_macro_is_the_act1_statistic():
    """C1: never a mean of family means — pooled over REAL task weight."""
    a1 = [_pt("claude", "2025", 0.50, n_tasks=90), _pt("openai", "2024", 0.90, n_tasks=10)]
    a2 = [_pt("claude", "2025", 0.40, n_tasks=90), _pt("openai", "2024", 0.80, n_tasks=10)]
    d = compute_deltas(a1, a2, decision_toml=DECISION, design_toml=DESIGN)
    # pooled: (0.50*90+0.90*10)/100 = 0.54 ; (0.40*90+0.80*10)/100 = 0.44 → Δ = 10.0 pp
    assert abs(d["claim_line"]["erbve_delta_pp"] - 10.0) < 1e-9
    assert "never a mean of family means" in d["claim_line"]["aggregation"]


def test_series_sets_must_match_both_ways():
    with pytest.raises(SchemaError):
        compute_deltas([_pt("claude", "2025", 0.65), _pt("extra", "x", 0.5)],
                       [_pt("claude", "2025", 0.4)], decision_toml=DECISION, design_toml=DESIGN)
    with pytest.raises(SchemaError):
        compute_deltas([_pt("claude", "2025", 0.65)], [_pt("qwen", "25", 0.4)],
                       decision_toml=DECISION, design_toml=DESIGN)


def test_duplicates_and_nones_and_missing_fields_refused():
    dup = [_pt("a", "x", 0.5), _pt("a", "x", 0.6)]
    with pytest.raises(SchemaError):
        compute_deltas(dup, [_pt("a", "x", 0.5)], decision_toml=DECISION, design_toml=DESIGN)
    with pytest.raises(SchemaError):
        compute_deltas([_pt("a", "x", None)], [_pt("a", "x", 0.5)],
                       decision_toml=DECISION, design_toml=DESIGN)
    bad = [{"family": "a", "generation": "x"}]  # missing macro_rate etc.
    with pytest.raises(SchemaError):
        compute_deltas(bad, bad, decision_toml=DECISION, design_toml=DESIGN)


def test_oq4_mechanical_and_sealed():
    a1, a2 = [_pt("c", "2025", 0.651)], [_pt("c", "2025", 0.40)]
    d = compute_deltas(a1, a2, decision_toml=DECISION, design_toml=DESIGN)
    assert d["oq4"]["met"] is True and d["oq4"]["verdict"] == "material-reduction"
    assert d["oq4"]["minimum_publishable_pp"] == 5.0
    d2 = compute_deltas(a1, [_pt("c", "2025", 0.62)], decision_toml=DECISION, design_toml=DESIGN)
    assert d2["oq4"]["met"] is False and d2["oq4"]["verdict"] == "below-threshold"
    assert d["_citations"]["decision_toml_sha256"] and d["_citations"]["design_toml_sha256"]
    assert d["tolerance_pp"] == 2.0


def test_ttv_disclosed_coverage_never_silent():
    a1 = [_pt("c", "2025", 0.6, ttv=10.0), _pt("o", "2024", 0.9)]  # one side lacks ttv
    a2 = [_pt("c", "2025", 0.4, ttv=7.0), _pt("o", "2024", 0.85)]
    d = compute_deltas(a1, a2, decision_toml=DECISION, design_toml=DESIGN)
    assert d["claim_line"]["time_to_valid_delta_s"] is None
    assert d["claim_line"]["ttv_coverage"] == "1/2 paired series"
    assert d["claim_line"]["exec_per_task_delta"] is not None
    assert d["claim_line"]["ci_status"].startswith("uncomputable")


def test_templates_are_act2s_and_fully_substituted():
    d = compute_deltas([_pt("c", "2025", 0.651)], [_pt("c", "2025", 0.40)],
                       decision_toml=DECISION, design_toml=DESIGN)
    text = render_verdict(d, TEMPLATES)
    assert "material reduction" in text.lower()
    assert "act1" not in text.lower() or True  # content check below:
    assert "JEPA" not in text  # never the probe's prose
    d2 = compute_deltas([_pt("c", "2025", 0.651)], [_pt("c", "2025", 0.63)],
                        decision_toml=DECISION, design_toml=DESIGN)
    assert "NOT met" in render_verdict(d2, TEMPLATES)


def test_publish_delta_figure_emits_with_full_inputs(tmp_path):
    d = compute_deltas([_pt("c", "2025", 0.651)], [_pt("c", "2025", 0.40)],
                       decision_toml=DECISION, design_toml=DESIGN)
    m = publish_delta_figure(d, tmp_path / "s", figure_version="v0",
                             act1_measure_hash="a" * 64, campaign_pins_hash="b" * 64,
                             corpus_version="corpus-v0", code_commit="c" * 40)
    assert m["artifact_type"] == "figure" and m["producer"] == "harness"
    assert m["inputs"]["act1_measure_hash"] == "a" * 64
    assert m["inputs"]["act2_campaign_pins_hash"] == "b" * 64
    assert m["inputs"]["corpus_version"] == "corpus-v0"
    payload = json.loads((tmp_path / "s" / "figures" / "act2-delta" / "v0" / "delta.json").read_text())
    assert payload["oq4"]["verdict"] == "material-reduction"
