"""Shadow-mode sampling + SM-C1 (story 7.4; FR-22 c3 — the MANDATED
measurement path for the false-block rate while blocking is on).

Pure: stdlib + core-schema only. Reuses the single Wilson-95 implementation
from ``gate.workload_check`` (never a second CI formula, never latent-gate).

Semantics
- A shadowed block is a blocking decision that is ALSO executed as an
  advisory twin (the patch runs anyway under observation) so its realized
  outcome is recorded against the block.
- ``FALSE BLOCK`` = the gate blocked, yet the realized outcome was
  ``valid_execution`` — the blocked patch actually flipped and passed. That is
  the over-blocking FR-22 budgets against (see the story-7.3 budget rationale).
- ``SM-C1`` = false_block_rate over shadowed blocks, with a Wilson 95% CI,
  compared against the pre-registered budget.

The sampler is deterministic, reproducible, and order-independent: membership
is a pure function of (salt, certificate_hash, patch_sha256). Binding the
certificate hash means a supersession (new certificate) intentionally re-rolls
who is shadowed — the sample is scoped to a specific authorization, matching
generation-scoped certificates (FR-21 c2). This story builds the mechanism and
demonstrates SM-C1 on a labeled synthetic pilot; actually running twins
requires a live block (story 7.5+).

Error code: LI-GATE-010 (shadow policy load + sampler/schema violations).
"""

from __future__ import annotations

import math
import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

from core_schema.errors import SchemaError

from gate.workload_check import wilson95_interval

SHADOW_IFACE_VERSION = "shadow-v1"

__all__ = [
    "SHADOW_IFACE_VERSION",
    "BudgetVerdict",
    "SMReport",
    "ShadowPolicy",
    "ShadowTwin",
    "compare_against_budget",
    "compute_sm_c1",
    "load_shadow_policy",
    "select_for_shadow",
]

_SHA = re.compile(r"[0-9a-f]{64}")
_REALIZED = Literal[
    "valid_execution",
    "false_start_tests_ran_no_flip",
    "false_start_infrastructure_failure",
]


@dataclass(frozen=True)
class ShadowPolicy:
    shadow_rate: float  # fraction of blocks shadowed, (0, 1]
    salt: str


@dataclass(frozen=True)
class ShadowTwin:
    patch_sha256: str
    certificate_hash: str
    realized_outcome: str

    @property
    def is_false_block(self) -> bool:
        """A blocked patch that actually flipped + passed = blocked wrongly."""
        return self.realized_outcome == "valid_execution"


@dataclass(frozen=True)
class SMReport:
    n_block_decisions: int
    n_sampled: int
    n_false_block: int
    false_block_rate: float | None      # None when n_sampled == 0 (honest)
    false_block_wilson95: tuple[float, float] | None
    sampled_share: float | None         # n_sampled / n_block_decisions


@dataclass(frozen=True)
class BudgetVerdict:
    within_budget: bool
    reason: str


def load_shadow_policy(path: Path) -> ShadowPolicy:
    """Fail-closed policy load (precedent: workload_check/budget). No defaults."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise SchemaError("LI-GATE-010", f"shadow policy unreadable: {p}",
                          {"err": type(exc).__name__}) from exc
    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-GATE-010", "shadow policy is not parseable TOML",
                          {"path": str(p)}) from exc
    sampling = doc.get("sampling")
    if not isinstance(sampling, dict):
        raise SchemaError("LI-GATE-010", "shadow policy must carry a [sampling] table", {})
    rate = sampling.get("shadow_rate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        raise SchemaError("LI-GATE-010", "sampling.shadow_rate must be numeric (strict bool)",
                          {"got": rate})
    rf = float(rate)
    if math.isnan(rf) or math.isinf(rf) or not 0.0 < rf <= 1.0:
        raise SchemaError("LI-GATE-010", "sampling.shadow_rate must lie in (0, 1]", {"got": rate})
    salt = sampling.get("salt", "")
    if not isinstance(salt, str):
        raise SchemaError("LI-GATE-010", "sampling.salt must be a string", {"got": salt})
    return ShadowPolicy(shadow_rate=rf, salt=salt)


def select_for_shadow(patch_sha256: str, certificate_hash: str, *,
                      shadow_rate: float, salt: str = "") -> bool:
    """Deterministic, reproducible, order-independent sampling decision."""
    if not (isinstance(patch_sha256, str) and _SHA.fullmatch(patch_sha256)):
        raise SchemaError("LI-GATE-010", "patch_sha256 must be 64-hex", {"got": patch_sha256})
    if not (isinstance(certificate_hash, str) and _SHA.fullmatch(certificate_hash)):
        raise SchemaError("LI-GATE-010", "certificate_hash must be 64-hex",
                          {"got": certificate_hash})
    if isinstance(shadow_rate, bool) or not isinstance(shadow_rate, (int, float)):
        raise SchemaError("LI-GATE-010", "shadow_rate must be numeric (strict bool)", {})
    r = float(shadow_rate)
    if math.isnan(r) or math.isinf(r) or not 0.0 < r <= 1.0:
        raise SchemaError("LI-GATE-010", "shadow_rate must lie in (0, 1]", {"got": shadow_rate})
    if r >= 1.0:
        return True
    identity = f"{salt}|{certificate_hash}|{patch_sha256}"
    u = int(sha256(identity.encode("utf-8")).hexdigest(), 16) / 2**256  # uniform [0,1)
    return u < r


def make_twin(patch_sha256: str, certificate_hash: str, realized_outcome: str) -> ShadowTwin:
    """Strict constructor: outcomes must be one of the judge-free LabelOutcome
    values (core_schema.domain); anything else is rejected, not coerced."""
    if not (isinstance(patch_sha256, str) and _SHA.fullmatch(patch_sha256)):
        raise SchemaError("LI-GATE-010", "patch_sha256 must be 64-hex", {})
    if not (isinstance(certificate_hash, str) and _SHA.fullmatch(certificate_hash)):
        raise SchemaError("LI-GATE-010", "certificate_hash must be 64-hex", {})
    allowed = ("valid_execution", "false_start_tests_ran_no_flip",
               "false_start_infrastructure_failure")
    if realized_outcome not in allowed:
        raise SchemaError("LI-GATE-010", "realized_outcome must be a judge-free LabelOutcome",
                          {"got": realized_outcome})
    return ShadowTwin(patch_sha256=patch_sha256, certificate_hash=certificate_hash,
                      realized_outcome=realized_outcome)


def compute_sm_c1(twins: Sequence[ShadowTwin], *, n_block_decisions: int) -> SMReport:
    """SM-C1 = false_block_rate over shadowed blocks, with Wilson 95% CI.

    ``false_block_rate`` is FRACTION; ``None`` when nothing was shadowed
    (honest undefined, never coerced to 0.0 — same honesty rule as 7.2)."""
    if isinstance(n_block_decisions, bool) or not isinstance(n_block_decisions, int) \
            or n_block_decisions < 0:
        raise SchemaError("LI-GATE-010", "n_block_decisions must be a non-negative integer",
                          {"got": n_block_decisions})
    n_sampled = len(twins)
    n_false = sum(1 for t in twins if t.is_false_block)
    rate = (n_false / n_sampled) if n_sampled else None
    wilson = wilson95_interval(n_false, n_sampled) if n_sampled else None
    share = (n_sampled / n_block_decisions) if n_block_decisions else None
    return SMReport(n_block_decisions=n_block_decisions, n_sampled=n_sampled,
                    n_false_block=n_false, false_block_rate=rate,
                    false_block_wilson95=wilson, sampled_share=share)


def compare_against_budget(report: SMReport, *, max_false_block_rate: float) -> BudgetVerdict:
    """None rate = no data = NOT within budget (FR-22 c1 honesty)."""
    if isinstance(max_false_block_rate, bool) or not isinstance(max_false_block_rate, (int, float)):
        raise SchemaError("LI-GATE-010", "max_false_block_rate must be numeric (strict bool)", {})
    b = float(max_false_block_rate)
    if math.isnan(b) or math.isinf(b) or not 0.0 < b < 1.0:
        raise SchemaError("LI-GATE-010", "max_false_block_rate must lie in (0,1)", {"got": b})
    if report.false_block_rate is None:
        return BudgetVerdict(False, "no shadowed blocks measured — false-block rate is "
                                    "undefined; undefined is not compliance (FR-22 c1)")
    ci = report.false_block_wilson95 or (0.0, 0.0)
    within = report.false_block_rate <= b
    state = "within" if within else "OVER"
    return BudgetVerdict(
        within_budget=within,
        reason=(f"false-block rate {report.false_block_rate:.4f} {state} budget "
                f"{b:.4f} (Wilson95 [{ci[0]:.4f}, {ci[1]:.4f}]; "
                f"{report.n_false_block}/{report.n_sampled} shadowed blocks)"))
