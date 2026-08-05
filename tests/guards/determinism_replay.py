"""Guard: labeling replay determinism (AD-7) — the CI hook proving byte-identity.

`assert_replay_determinism` is the reusable hook: run any pure labeling function
twice on frozen inputs; outputs must be byte-identical.
"""

from __future__ import annotations

import json


def toy_label(attempt: dict, rules: dict) -> dict:
    """Pure stand-in for rules_v1: label = f(inputs, ruleset)."""
    return {
        "attempt_id": attempt["attempt_id"],
        "outcome": "valid_execution" if "1 passed" in attempt["raw_output"] else "false_start",
        "ruleset_version": rules["version"],
        "schema_version": 1,
    }


def serialize_labels(labels: list[dict]) -> bytes:
    return (json.dumps(labels, sort_keys=True, separators=(",", ":")) + "\n").encode()


def run_labeling(attempts, rules) -> bytes:
    return serialize_labels([toy_label(a, rules) for a in attempts])


def assert_replay_determinism(run, *args) -> bytes:
    first = run(*args)
    second = run(*args)
    assert first == second, "labeling replay is not byte-identical"
    return first
