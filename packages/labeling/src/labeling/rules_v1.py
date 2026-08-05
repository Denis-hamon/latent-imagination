"""rules-v1: frozen classification rule set (pure functions over test output).

Edit discipline: any change to RULES bumps ruleset_version and re-anchors; the
frozen decision tree (governance/labeling-decision-tree.md) documents each rule.
"""

from __future__ import annotations

from core_schema.domain import LabelOutcome

RULESET_VERSION = "rules-v1"
SCHEMA_VERSION = 1

# inference order: infra signals first (they poison test verdicts), then flip.
INFRA_PATTERNS = [
    "segmentation fault",
    "no space left on device",
    "docker: error",
    "container failed to start",
    "network is unreachable",
    "modulenotfounderror",  # env broken, not agent error
    "modulenotfounderror:",
    "internal server error",
]

FLIP_PATTERNS = ["1 passed", "all tests passed", "ok\n", "0 failed"]

AMBIGUOUS_PATTERNS = ["timeout", "timed out", "killed", "panic:"]


def classify_tests_output(raw_output: str) -> LabelOutcome | None:
    """None == ambiguous → route to quarantine, never adjudicate by judgment."""
    low = raw_output.lower()
    for p in INFRA_PATTERNS:
        if p in low:
            return LabelOutcome.FALSE_START_INFRASTRUCTURE_FAILURE
    for p in AMBIGUOUS_PATTERNS:
        if p in low:
            return None
    for p in FLIP_PATTERNS:
        if p in low:
            return LabelOutcome.VALID_EXECUTION
    return LabelOutcome.FALSE_START_TESTS_RAN_NO_FLIP
