"""Proof tests for the AD-7 replay determinism hook."""

from __future__ import annotations

import pytest

from tests.guards.determinism_replay import (
    assert_replay_determinism,
    run_labeling,
    serialize_labels,
    toy_label,
)


def test_replay_byte_identical():
    attempts = [
        {"attempt_id": "a" * 64, "raw_output": "1 passed in 0.1s"},
        {"attempt_id": "b" * 64, "raw_output": "segmentation fault"},
    ]
    assert_replay_determinism(run_labeling, attempts, {"version": "rules-v1"})


def test_guard_detects_nondeterminism():
    state = {"n": 0}

    def flaky_run(attempts, rules):
        state["n"] += 1
        return serialize_labels(
            [dict(toy_label(a, rules), run_n=state["n"]) for a in attempts]
        )

    attempts = [{"attempt_id": "a" * 64, "raw_output": "1 passed"}]
    with pytest.raises(AssertionError, match="not byte-identical"):
        assert_replay_determinism(flaky_run, attempts, {"version": "rules-v1"})
