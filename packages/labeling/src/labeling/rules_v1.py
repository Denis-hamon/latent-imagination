"""rules-v1: frozen classification rule set (pure functions over test output).

Hardened (review 2026-08-05):
- NEGATIVE evidence precedence: any explicit failure marker forbids a flip label
- CRLF/Unicode hygiene: raw output is normalized (\\r\\n→\\n) before matching
- patterns are word-boundary-aware where it matters (no "0 timeouts" traps)
- a passing-looking line that names a failure is INFRA/ambiguous, never valid

Edit discipline: any change bumps RULESET_VERSION and re-anchors.
"""

from __future__ import annotations

from core_schema.domain import LabelOutcome

RULESET_VERSION = "rules-v1"
SCHEMA_VERSION = 1

INFRA_PATTERNS = [
    "segmentation fault",
    "segmentationfault",
    "no space left on device",
    "docker: error",
    "container failed to start",
    "network is unreachable",
    "modulenotfounderror",
]

# explicit failure markers — if ANY is present, a flip verdict is forbidden
NEGATIVE_MARKERS = [
    " failed",
    "failed:",
    "errors",
    "error ",
    "traceback (most recent call last)",
]

# must appear to accept a flip (after negatives are ruled out). "ok\n" survives
# post-CRLF-normalization: "OK\r\n" from Windows/unittest CI → "ok\n" ✓ (EC-6).
FLIP_PATTERNS = ["passed", "ok\n"]

# timeouts/killed are ambiguous UNLESS the same output also says "0 timeouts"
AMBIGUOUS_PATTERNS = ["timed out", "timeout", "killed", "panic:"]
AMBIGUITY_EXCUSES = ["0 timeouts", "0 timed out"]


def classify_tests_output(raw_output: str) -> LabelOutcome | None:
    """None == ambiguous → quarantine. Never adjudicate by judgment."""
    text = raw_output.replace("\r\n", "\n").replace("\r", "\n").lower()
    for p in INFRA_PATTERNS:
        if p in text:
            return LabelOutcome.FALSE_START_INFRASTRUCTURE_FAILURE
    has_negative = any(p in text for p in NEGATIVE_MARKERS)
    has_flip = any(p in text for p in FLIP_PATTERNS)
    has_ambiguous = any(p in text for p in AMBIGUOUS_PATTERNS) and not any(
        e in text for e in AMBIGUITY_EXCUSES
    )
    # order of evidence: negatives kill flips first; ambiguity only without
    # an explicit failure; else a clean flip marker is accepted.
    if has_negative:
        return LabelOutcome.FALSE_START_TESTS_RAN_NO_FLIP
    if has_ambiguous:
        return None
    if has_flip:
        return LabelOutcome.VALID_EXECUTION
    if not text.strip():
        # empty output: no tests demonstrably ran → no-flip false start
        return LabelOutcome.FALSE_START_TESTS_RAN_NO_FLIP
    return LabelOutcome.FALSE_START_TESTS_RAN_NO_FLIP
