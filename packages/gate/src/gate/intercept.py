"""Vendor-neutral interception interface (story 5.1, FR-18/FR-19).

One seam for every adapter: a pre-execution callback IN, an annotated
response OUT, every decision appended to the deployer-local log. Advisory by
CONSTRUCTION: there is no blocking code path in this package — nothing here
returns or raises a "halt execution" signal. FR-21's blocking mode is a
different phase's package with measured-precision certificates; wiring it here
would be a doctrine violation.

Annotations are StoreEvents (kind `gate_annotated`) — the deployed telemetry
speaks the Trace Schema like everything else.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Protocol

from core_schema.errors import SchemaError
from core_schema.events import StoreEvent

from gate.ports import INTERFACE_VERSION, PinnedSnapshot


class CandidatePatchCtx(Protocol):
    """What any adapter must supply about a pre-execution candidate."""

    repo: str
    patch_diff: str
    attempt_start_hint: datetime | None  # adapter clock hint; log time is authoritative


class Annotation(Protocol):
    event: StoreEvent
    rationale_ptr: str  # pointer to the methodology doc, never a narrated sim


def annotate(
    snapshot: PinnedSnapshot,
    *,
    flip_probability: float,
    model_family: str,
    latency_s: float,
    disclosure: dict[str, Any],
    now: datetime | None = None,
) -> StoreEvent:
    """Build the annotated response as a Trace-Schema event.

    `disclosure` is MANDATORY and must carry the sub-bar posture — an
    annotation that hides the predictor's measured precision is refused.
    """
    if not (0.0 <= flip_probability <= 1.0):
        raise SchemaError("LI-GATE-002", "flip_probability outside [0,1]", {"got": flip_probability})
    if not isinstance(disclosure, dict) or "measured_precision" not in disclosure:
        raise SchemaError(
            "LI-GATE-002", "annotation lacks predictor disclosure (measured_precision)",
            {"keys": sorted(disclosure) if isinstance(disclosure, dict) else None},
        )
    ts = now or datetime.now(UTC)
    return StoreEvent(
        schema_version=1,
        kind="gate_annotated",
        occurred_at=ts,
        payload={
            "interface_version": INTERFACE_VERSION,
            "predictor_hash": snapshot.predictor_hash,
            "predictor_version": snapshot.predictor_version,
            "corpus_version": snapshot.corpus_version,
            "flip_probability": flip_probability,
            "model_family": model_family,
            "latency_s": round(latency_s, 6),
            "predictor_disclosure": disclosure,
        },
    )


def timed(fn, *args, **kwargs):
    """Latency instrumentation helper (NFR-P1 path) — returns (result, seconds)."""
    t0 = time.perf_counter()
    res = fn(*args, **kwargs)
    return res, time.perf_counter() - t0
