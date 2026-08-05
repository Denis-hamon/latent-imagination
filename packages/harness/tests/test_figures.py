"""Figures: claim/context separation, counts on every point, five-second headline."""

from __future__ import annotations

from harness.figures import Taxonomy, erbve_curve, headline

ATTEMPTS = {
    "a1": ("t1", "2026-08-05T10:00:00Z", ("claude", "2025")),
    "a2": ("t1", "2026-08-05T10:01:00Z", ("claude", "2025")),
    "a3": ("t1", "2026-08-05T10:02:00Z", ("claude", "2025")),
    "b1": ("t2", "2026-08-05T10:00:00Z", ("codex", "2025")),
    "b2": ("t2", "2026-08-05T10:01:00Z", ("codex", "2025")),
    "x1": ("t9", "2026-08-05T10:00:00Z", ("archive", "2023")),
    "x2": ("t9", "2026-08-05T10:01:00Z", ("archive", "2023")),
}
LABELS = [
    {"attempt_id": "a1", "outcome": "false_start_tests_ran_no_flip"},
    {"attempt_id": "a2", "outcome": "false_start_tests_ran_no_flip"},
    {"attempt_id": "a3", "outcome": "valid_execution"},
    {"attempt_id": "b1", "outcome": "false_start_tests_ran_no_flip"},
    {"attempt_id": "b2", "outcome": "false_start_tests_ran_no_flip"},
    {"attempt_id": "x1", "outcome": "false_start_tests_ran_no_flip"},
    {"attempt_id": "x2", "outcome": "false_start_tests_ran_no_flip"},
]

TAX = Taxonomy(
    claim_series=frozenset({("claude", "2025"), ("codex", "2025")}),
    context_series=frozenset({("archive", "2023")}),
)


def _curve():
    return erbve_curve(
        LABELS,
        task_of_attempt=lambda a: ATTEMPTS[a][0],
        start_of_attempt=lambda a: ATTEMPTS[a][1],
        series_of_attempt=lambda a: ATTEMPTS[a][2],
        taxonomy=TAX,
    )


def test_points_carry_counts_and_claim_flag():
    fig = _curve()
    by_key = {(p["family"], p["generation"]): p for p in fig["points"]}
    claude = by_key[("claude", "2025")]
    assert claude["claim"] is True
    assert abs(claude["macro_rate"] - 2 / 3) < 1e-12  # 2 of 3 before valid
    assert claude["total_attempts"] == 3
    assert by_key[("archive", "2023")]["claim"] is False


def test_context_never_enters_claim_line():
    fig = _curve()
    # claim series only: claude (2/3) + codex (1.0) → macro ≈ 0.833
    expected = (2 / 3 + 1.0) / 2
    assert abs(fig["claim_line"]["macro_rate"] - expected) < 1e-12
    # if context leaked in, macro would be (2/3+1+1)/3 ≈ 0.888


def test_five_second_headline_shape():
    h = headline(_curve())
    # claim: claude 2 false/3 attempts + codex 2 false/2 attempts = 4/5
    assert h == "4 attempts out of 5 failed to pass the task's tests before a valid execution ran."


def test_no_data_is_not_perfect_zero():
    fig = erbve_curve(
        [], task_of_attempt=lambda a: None, start_of_attempt=lambda a: "",
        series_of_attempt=lambda a: ("x", "y"), taxonomy=TAX,
    )
    assert fig["claim_line"]["macro_rate"] is None
    assert headline(fig) == "0 attempts out of 0 failed to pass the task's tests before a valid execution ran."
