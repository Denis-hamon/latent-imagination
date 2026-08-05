"""Hardening-lite criteria for the probe clean slice (Story 3.1, FR-16 lite).

Three cheap, literature-anchored rejectors over ITEM METADATA ONLY
(no code parsing — that's Epic 4's full detector):

1. **Infra/config F2P**: the task's fail-to-pass tests live in conftest.py,
   CI-config paths, or non-`.py` test drivers — validity would not measure
   semantic correctness.
2. **Test-only gold patch**: the reference fix changes NO source file — there
   is nothing to predict (the task is a test edit).
3. **Known-weak overlap** (if a published hackability list is ingestible):
   instance ids intersecting it are rejected.

Everything is logged with the reject rate for disclosure beside every figure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

INFRA_TEST_PATH = re.compile(r"(conftest\.py|\.github/|/ci/|setup\.py|tox\.ini)", re.IGNORECASE)
SOURCE_GLOB = re.compile(r"^(?!.*test).*\.py$")  # test-path-ish is excluded separately


@dataclass(frozen=True)
class Reject:
    instance_id: str
    reason: str


def _is_test_path(p: str) -> bool:
    low = p.lower()
    return "test" in low or low.endswith("conftest.py")


def reject_reasons(item: dict[str, Any], known_hackable: set[str] | None = None) -> list[str]:
    reasons: list[str] = []
    iid = item.get("instance_id", "?")

    # (1) infra/config F2P paths
    f2p = item.get("FAIL_TO_PASS") or []
    if any(INFRA_TEST_PATH.search(t or "") for t in f2p):
        reasons.append("f2p-infra-config")

    # (2) test-only gold patch: patch touches no non-test .py file
    patch = item.get("patch") or ""
    touched = re.findall(r"^\+\+\+ b/(.+)$", patch, re.MULTILINE)
    src_touched = [p for p in touched if p.endswith(".py") and "test" not in p.lower()]
    if not src_touched:
        reasons.append("test-only-patch")

    # (3) known-weak overlap (optional input; absence is not fatal)
    if known_hackable and iid in known_hackable:
        reasons.append("known-weak-suite")

    return reasons


def filter_slice(items: list[dict[str, Any]], known_hackable: set[str] | None = None) -> tuple[list[dict[str, Any]], list[Reject]]:
    kept: list[dict[str, Any]] = []
    rejected: list[Reject] = []
    for it in items:
        reasons = reject_reasons(it, known_hackable)
        if reasons:
            rejected.append(Reject(it.get("instance_id", "?"), ",".join(reasons)))
        else:
            kept.append(it)
    return kept, rejected
