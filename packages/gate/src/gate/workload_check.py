"""Per-deployment workload precision check (story 7.2; FR-21 c1).

The protocol this module implements lives in
``governance/gate/workload-check-protocol.md`` — "the gate measures precision
from my deployer-local labeled history and enables blocking only strictly
above the bar".

Measurement honesty (OQ-10 resolution; FR-3/FR-9):
- only annotations that JOIN a realized outcome enter the denominator;
  abstentions (``prediction_refused``) and unmatched predictions are counted
  and disclosed, never counted as evidence. No invented denominator.
- ground truth is the judge-free F2P outcome of ``labeling/rules_v1.py``:
  ``valid_execution`` -> flip observed (1); both ``false_start_*`` -> 0 (an
  infrastructure failure means the flip was NOT observed — the conservative
  F2P reading; quarantine rows are never Labels and never reach here).
- binarization mirrors the probe training regime: flip predicted iff
  ``flip_probability > binarization_threshold`` (strict; default 0.5 = the
  sklearn LogReg ``predict()`` boundary used by ``probe.arms.baseline``).
  The threshold is a pre-registered policy value, loaded fail-closed.

Strictness regimes (deliberately distinct — never unify):
- probe verdict crossing: ``precision >= bar`` (decision.toml [strictness])
- blocking authorization: ``precision >  bar`` (FR-21, this module)

Units: FRACTIONS in every payload/report field; ``_pp`` display suffixes only
in human-facing strings (Epic 6 lesson). Confidence scores are never an input:
``WorkloadRow`` forbids every field outside the protocol's four (extra keys —
``confidence``, ``score``, anything — are validation errors, not ignored).

Error code: LI-GATE-008 (policy load and row-schema violations).
"""

from __future__ import annotations

import math
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from core_schema.domain import StrictModel
from core_schema.errors import SchemaError
from core_schema.events import StoreEvent
from pydantic import field_validator

WORKLOAD_CHECK_IFACE_VERSION = "workload-check-v1"

__all__ = [
    "WORKLOAD_CHECK_IFACE_VERSION",
    "CheckVerdict",
    "FreshnessVerdict",
    "WorkloadPolicy",
    "WorkloadPrecisionReport",
    "WorkloadRow",
    "authorization_state",
    "check_against_bar",
    "load_workload_policy",
    "measure_workload_precision",
    "wilson95_interval",
    "workload_checked_event",
]

_TIER = Literal["diff_touched", "user_designated"]
_OUTCOME = Literal[
    "valid_execution",
    "false_start_tests_ran_no_flip",
    "false_start_infrastructure_failure",
]


class WorkloadRow(StrictModel):
    """One joined measurement row — protocol field set, closed.

    `extra="forbid"` is the mechanical encoding of FR-21's "confidence scores
    are never an input": smuggling a confidence/score/tier-weight key raises.
    """

    patch_sha256: str
    flip_probability: float
    prediction_target_tier: _TIER
    outcome: _OUTCOME

    @field_validator("patch_sha256")
    @classmethod
    def _sha(cls, v: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", v):
            raise ValueError("patch_sha256 must be 64-hex")
        return v

    @field_validator("flip_probability", mode="before")
    @classmethod
    def _prob_bool(cls, v: Any) -> Any:
        # strict-bool (Epic 6 F4): True is not 1.0 here; reject before coercion
        if isinstance(v, bool):
            raise ValueError("flip_probability must be numeric, not bool")  # noqa: TRY004
        return v

    @field_validator("flip_probability")
    @classmethod
    def _prob_range(cls, v: float) -> float:
        # runs after pydantic coercion — catches strings coerced to out-of-range
        if math.isnan(v) or math.isinf(v):
            raise ValueError("flip_probability must be finite")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"flip_probability must be in [0,1], got {v}")
        return v


@dataclass(frozen=True)
class WorkloadPrecisionReport:
    """Counts + precision in FRACTIONS; precision None == no positive
    predictions (honest undefined, never coerced to 0.0 — probe precedent)."""

    n: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float | None
    precision_wilson95: tuple[float, float] | None
    binarization_threshold: float
    prediction_target_tiers: tuple[str, ...]


@dataclass(frozen=True)
class CheckVerdict:
    blocking_enabled: bool
    reason: str
    precision: float | None
    registered_bar: float | None  # None when the certificate failed to authorize


@dataclass(frozen=True)
class WorkloadPolicy:
    max_age_days: int
    binarization_threshold: float


@dataclass(frozen=True)
class FreshnessVerdict:
    blocking_permitted: bool
    reason: str
    last_checked_at: str | None


def wilson95_interval(k: int, n: int) -> tuple[float, float]:
    """Wilson score interval, z=1.96, clamped to [0,1].

    The pre-registered CI method (governance/probe-design/decision.toml
    [metric] ci_method = "wilson score interval, 95% two-sided"). n=0 ->
    (0.0, 0.0): no data, no interval, no invention.
    """
    if not isinstance(k, int) or not isinstance(n, int) or isinstance(k, bool) or isinstance(n, bool):
        raise SchemaError("LI-GATE-008", "wilson95_interval takes exact int counts", {})
    if k < 0 or n < 0 or k > n:
        raise SchemaError("LI-GATE-008", "wilson95_interval requires 0 <= k <= n",
                          {"k": k, "n": n})
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    zz = z * z
    phat = k / n
    denom = 1.0 + zz / n
    center = phat + zz / (2.0 * n)
    margin = z * math.sqrt(phat * (1.0 - phat) / n + zz / (4.0 * n * n))
    return (max(0.0, (center - margin) / denom), min(1.0, (center + margin) / denom))


def measure_workload_precision(
    rows: Sequence[WorkloadRow],
    *,
    binarization_threshold: float = 0.5,
) -> WorkloadPrecisionReport:
    """tp/fp/fn/tn over joined rows; precision on positive predictions only."""
    if isinstance(binarization_threshold, bool) or not isinstance(binarization_threshold, (int, float)):
        raise SchemaError("LI-GATE-008", "binarization_threshold must be numeric (strict bool)", {})
    thr = float(binarization_threshold)
    if math.isnan(thr) or math.isinf(thr) or not 0.0 < thr < 1.0:
        raise SchemaError("LI-GATE-008",
                          "binarization_threshold must lie strictly inside (0,1)",
                          {"got": thr})
    tp = fp = fn = tn = 0
    for r in rows:
        pred = r.flip_probability > thr
        truth = r.outcome == "valid_execution"
        if pred and truth:
            tp += 1
        elif pred and not truth:
            fp += 1
        elif not pred and truth:
            fn += 1
        else:
            tn += 1
    n_pos = tp + fp
    precision = (tp / n_pos) if n_pos else None
    wilson = wilson95_interval(tp, n_pos) if n_pos else None
    tiers = tuple(sorted({r.prediction_target_tier for r in rows}))
    return WorkloadPrecisionReport(
        n=len(rows), tp=tp, fp=fp, fn=fn, tn=tn,
        precision=precision, precision_wilson95=wilson,
        binarization_threshold=thr, prediction_target_tiers=tiers)


def check_against_bar(report: WorkloadPrecisionReport, *, registered_bar: float) -> CheckVerdict:
    """FR-21 strictly-above: at or below the bar, advisory stays on."""
    if isinstance(registered_bar, bool) or not isinstance(registered_bar, (int, float)):
        raise SchemaError("LI-GATE-008", "registered_bar must be numeric (strict bool)", {})
    bar = float(registered_bar)
    if math.isnan(bar) or math.isinf(bar) or not 0.0 <= bar <= 1.0:
        raise SchemaError("LI-GATE-008", "registered_bar must lie in [0,1]", {"got": bar})
    if report.precision is None:
        return CheckVerdict(
            blocking_enabled=False,
            reason="no positive predictions in the workload history — precision is "
                   "undefined; advisory stays on (OQ-10: no invented denominator)",
            precision=None, registered_bar=bar)
    above = report.precision > bar
    wilson = report.precision_wilson95 or (0.0, 0.0)
    if above:
        reason = (f"local workload precision {report.precision:.4f} strictly above "
                  f"bar {bar:.4f} (Wilson95 [{wilson[0]:.4f}, {wilson[1]:.4f}], "
                  f"n={report.n}) — blocking authorized by this check")
    else:
        reason = (f"local workload precision {report.precision:.4f} at/below bar "
                  f"{bar:.4f} (Wilson95 [{wilson[0]:.4f}, {wilson[1]:.4f}], "
                  f"n={report.n}) — advisory stays on (FR-21 strictly-above)")
    return CheckVerdict(blocking_enabled=above, reason=reason,
                        precision=report.precision, registered_bar=bar)


def load_workload_policy(path: Path) -> WorkloadPolicy:
    """Fail-closed policy load (precedent: gate.bench.load_budget). No defaults."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise SchemaError("LI-GATE-008", f"workload policy unreadable: {p}",
                          {"err": type(exc).__name__}) from exc
    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-GATE-008", "workload policy is not parseable TOML",
                          {"path": str(p)}) from exc
    cadence = doc.get("cadence")
    measurement = doc.get("measurement")
    if not isinstance(cadence, dict) or not isinstance(measurement, dict):
        raise SchemaError("LI-GATE-008",
                          "workload policy must carry [cadence] and [measurement] tables", {})
    days = cadence.get("max_age_days")
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise SchemaError("LI-GATE-008", "cadence.max_age_days must be a positive integer",
                          {"got": days})
    thr = measurement.get("binarization_threshold")
    if isinstance(thr, bool) or not isinstance(thr, (int, float)):
        raise SchemaError("LI-GATE-008",
                          "measurement.binarization_threshold must be numeric (strict bool)",
                          {"got": thr})
    if not 0.0 < float(thr) < 1.0:
        raise SchemaError("LI-GATE-008",
                          "measurement.binarization_threshold must lie strictly inside (0,1)",
                          {"got": thr})
    return WorkloadPolicy(max_age_days=days, binarization_threshold=float(thr))


def _parse_check_time(value: Any) -> datetime | None:
    """tz-aware parse; naive/unparseable -> None (caller fails closed)."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt


def authorization_state(
    decision_rows: Sequence[Mapping[str, Any]],
    *,
    max_age: timedelta,
    now: datetime,
) -> FreshnessVerdict:
    """Freshness rule: an absent, stale, or negative latest check authorizes
    nothing. Fail-closed on malformed records (no truthiness, no crashes)."""
    checks: list[tuple[datetime, Mapping[str, Any]]] = []
    for row in decision_rows:
        if row.get("kind") != "workload_checked":
            continue
        ts = _parse_check_time(row.get("occurred_at"))
        payload = row.get("payload")
        if ts is None or not isinstance(payload, Mapping):
            continue  # malformed record never authorizes
        checks.append((ts, payload))
    if not checks:
        return FreshnessVerdict(False, "no workload check on record — blocking off", None)
    ts, payload = max(checks, key=lambda pair: pair[0])
    last_iso = ts.isoformat()
    if now - ts > max_age:
        return FreshnessVerdict(False,
                                f"workload check expired ({last_iso} older than "
                                f"{max_age.days}d policy) — blocking off until re-run",
                                last_iso)
    enabled = payload.get("blocking_enabled")
    if enabled is True:
        return FreshnessVerdict(True, f"fresh workload check enabled blocking ({last_iso})",
                                last_iso)
    if enabled is False:
        reason = payload.get("reason")
        return FreshnessVerdict(False,
                                reason if isinstance(reason, str) and reason.strip()
                                else "latest workload check did not enable blocking",
                                last_iso)
    return FreshnessVerdict(False,
                            "latest workload check record malformed (blocking_enabled not "
                            "strict bool) — fail-closed", last_iso)


def workload_checked_event(
    *,
    certificate_hash: str,
    generation: str,
    report: WorkloadPrecisionReport,
    verdict: CheckVerdict,
    policy: WorkloadPolicy,
    now: datetime | None = None,
) -> StoreEvent:
    """Occurrence event for the deployer-local decision log (append_decision).

    ``registered_bar`` may be None when the certificate failed to authorize
    (no bar to measure against) — recorded as JSON null, never invented."""
    if not re.fullmatch(r"[0-9a-f]{64}", certificate_hash):
        raise SchemaError("LI-GATE-008", "certificate_hash must be 64-hex for the event", {})
    if not isinstance(generation, str) or not generation.strip():
        raise SchemaError("LI-GATE-008", "generation must be a non-empty string", {})
    payload: dict[str, Any] = {
        "interface_version": WORKLOAD_CHECK_IFACE_VERSION,
        "certificate_hash": certificate_hash,
        "generation": generation,
        "n": report.n, "tp": report.tp, "fp": report.fp,
        "fn": report.fn, "tn": report.tn,
        "precision": report.precision,
        "precision_wilson95": list(report.precision_wilson95)
        if report.precision_wilson95 else None,
        "binarization_threshold": report.binarization_threshold,
        "registered_bar": verdict.registered_bar,
        "blocking_enabled": verdict.blocking_enabled,
        "reason": verdict.reason,
        "max_age_days": policy.max_age_days,
        "prediction_target_tiers": list(report.prediction_target_tiers),
    }
    return StoreEvent(schema_version=1, kind="workload_checked",
                      occurred_at=now or datetime.now(UTC), payload=payload)
