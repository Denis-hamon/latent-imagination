"""ERBVE arithmetic proof vs hand-computed worked examples (Glossary fidelity)."""

from __future__ import annotations

from harness.metrics import compute_erbve

# Fixture attempts:
# Task A: attempts at t1(fail), t2(fail), t3(valid) -> counted 3, false 2 -> 2/3
# Task B: attempts t1(fail), t2(fail) -> never valid -> counted 2, false 2 -> 1.0
# Task C: attempt t1(valid) -> counted 1, false 0 -> 0.0
ATTEMPTS = {
    "a1": ("A", "2026-08-05T10:00:00Z"),
    "a2": ("A", "2026-08-05T10:01:00Z"),
    "a3": ("A", "2026-08-05T10:02:00Z"),
    "b1": ("B", "2026-08-05T10:00:00Z"),
    "b2": ("B", "2026-08-05T10:01:00Z"),
    "c1": ("C", "2026-08-05T10:00:00Z"),
}
LABELS = [
    {"attempt_id": "a1", "outcome": "false_start_tests_ran_no_flip"},
    {"attempt_id": "a2", "outcome": "false_start_infrastructure_failure"},
    {"attempt_id": "a3", "outcome": "valid_execution"},
    {"attempt_id": "b1", "outcome": "false_start_tests_ran_no_flip"},
    {"attempt_id": "b2", "outcome": "false_start_tests_ran_no_flip"},
    {"attempt_id": "c1", "outcome": "valid_execution"},
]


def test_metric_matches_hand_computed_glossary_example():
    rep = compute_erbve(
        LABELS,
        task_of_attempt=lambda a: ATTEMPTS[a][0],
        start_of_attempt=lambda a: ATTEMPTS[a][1],
    )
    by_task = {t.task_id: t for t in rep.per_task}
    assert by_task["A"].attempts_counted == 3 and by_task["A"].false_starts == 2
    assert abs(by_task["A"].rate - 2 / 3) < 1e-12
    assert by_task["B"].rate == 1.0 and by_task["B"].reached_valid is False
    assert by_task["C"].rate == 0.0 and by_task["C"].reached_valid is True
    macro = (2 / 3 + 1.0 + 0.0) / 3
    assert abs(rep.macro_rate - macro) < 1e-12
    assert rep.total_attempts == 6 and rep.total_false_starts == 4
    assert abs(rep.micro_rate - 4 / 6) < 1e-12


def test_post_valid_attempts_not_counted():
    labels = LABELS + [
        {"attempt_id": "a4", "outcome": "false_start_tests_ran_no_flip"},
    ]
    attempts2 = dict(ATTEMPTS)
    attempts2["a4"] = ("A", "2026-08-05T10:03:00Z")  # after a3 (valid)
    rep = compute_erbve(
        labels,
        task_of_attempt=lambda a: attempts2[a][0],
        start_of_attempt=lambda a: attempts2[a][1],
    )
    # a4 must NOT be counted: A's first valid (a3) precedes it
    assert rep.total_attempts == 6


def test_infra_failures_are_false_starts_not_excluded():
    # a2 is an infrastructure failure; Task A rate includes it (2/3, not 1/2)
    rep = compute_erbve(
        LABELS,
        task_of_attempt=lambda a: ATTEMPTS[a][0],
        start_of_attempt=lambda a: ATTEMPTS[a][1],
    )
    by_task = {t.task_id: t for t in rep.per_task}
    assert by_task["A"].false_starts == 2
