"""Act II delta computation (story 6.2): Act I discipline, OQ-4 mechanical,
sealed citations."""

from __future__ import annotations

from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from harness.delta import compute_deltas, render_verdict

REPO = Path(__file__).resolve().parents[3]
DECISION = REPO / "governance" / "probe-design" / "decision.toml"
DESIGN = REPO / "governance" / "act1-design" / "design.toml"
TEMPLATES = REPO / "governance" / "probe-design" / "verdict-templates"


def _pt(fam, gen, macro, attempts=100, ttv=None):
    p = {"family": fam, "generation": gen, "macro_rate": macro, "micro_rate": macro,
         "total_attempts": attempts, "total_false_starts": int(attempts * macro), "n_tasks": 10}
    if ttv is not None:
        p["mean_time_to_valid_s"] = ttv
    return p


def test_material_reduction_branch():
    a1 = [_pt("claude", "2025", 0.651, ttv=10.0), _pt("openai", "2024", 0.981, ttv=12.0)]
    a2 = [_pt("claude", "2025", 0.40, ttv=7.0), _pt("openai", "2024", 0.85, ttv=9.0)]
    d = compute_deltas(a1, a2, decision_toml=DECISION, design_toml=DESIGN)
    # macro claim line: ((0.651+0.981)/2 - (0.40+0.85)/2) * 100 ≈ 19.05 pp ≥ 5 → material
    assert d["oq4"]["met"] is True and d["oq4"]["verdict"] == "material-reduction"
    assert d["oq4"]["minimum_publishable_pp"] == 5.0  # read from the SEALED file
    assert d["tolerance_pp"] == 2.0
    assert abs(d["claim_line"]["erbve_delta_pp"] - 19.10) < 0.01  # (0.816−0.625)·100
    assert abs(d["claim_line"]["time_to_valid_delta_s"] - (-3.0)) < 1e-9  # 8−11
    assert d["_citations"]["decision_toml_sha256"]


def test_below_threshold_states_exactly_that():
    d = compute_deltas([_pt("claude", "2025", 0.651)], [_pt("claude", "2025", 0.62)],
                       decision_toml=DECISION, design_toml=DESIGN)
    assert d["oq4"]["met"] is False
    assert d["oq4"]["verdict"] == "below-threshold-measurement-only"


def test_unpinned_act2_series_refused():
    with pytest.raises(SchemaError) as ei:
        compute_deltas([_pt("claude", "2025", 0.65)], [_pt("qwen", "2025", 0.4)],
                       decision_toml=DECISION, design_toml=DESIGN)
    assert ei.value.code == "LI-HARNESS-020"


def test_verdict_templates_render_anchored():
    for a2_rate, frag in ((0.40, "margin met"), (0.64, "NOT met")):
        d = compute_deltas([_pt("claude", "2025", 0.651)], [_pt("claude", "2025", a2_rate)],
                           decision_toml=DECISION, design_toml=DESIGN)
        text = render_verdict(d, TEMPLATES)
        assert "{delta}" not in text
        assert isinstance(text, str) and len(text) > 20
