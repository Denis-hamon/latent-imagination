"""Vendor-neutral interception interface (story 5.1 + CR, FR-18/FR-19).

One seam for every adapter: a CandidateCtx IN, an annotated StoreEvent OUT,
every decision appended to the deployer-local log. Advisory by CONSTRUCTION:
no public callable returns or signals "halt execution". FR-21's blocking mode
is a different phase's package with measured-precision certificates.

Abstention is a first-class event (`prediction_refused`) — per the OQ-10
resolution, a gate without a denominator emits silence-on-purpose, recorded.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from core_schema.errors import SchemaError
from core_schema.events import StoreEvent

from gate.ports import _SHA_RE, INTERFACE_VERSION, PinnedSnapshot


@dataclass(frozen=True)
class CandidateCtx:
    """The subject of an annotation — an annotation without a subject is not one."""

    repo: str
    patch_diff: str
    rationale_ptr: str  # methodology doc pointer, never a narrated simulation
    # hash of the raw wire payload the adapter received (the reconstructed diff
    # is hash-addressed separately via patch_sha256 — naming both kills the
    # "anchored to a reconstruction" ambiguity, CR 5.5)
    wire_payload_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "_patch_sha256", sha256(self.patch_diff.encode()).hexdigest())

    @property
    def patch_sha256(self) -> str:
        return self._patch_sha256  # computed once (CR 5.4: hot path never re-hashes)


def _check_number(name: str, v: Any, lo: float, hi: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SchemaError("LI-GATE-002", f"{name} must be numeric", {"got": type(v).__name__})
    f = float(v)
    if math.isnan(f) or math.isinf(f) or not (lo <= f <= hi):
        raise SchemaError("LI-GATE-002", f"{name} outside [{lo},{hi}] or non-finite", {"got": f})
    return f


def _check_disclosure(disclosure: Any, snapshot: PinnedSnapshot) -> dict:
    if not isinstance(disclosure, dict):
        raise SchemaError("LI-GATE-002", "predictor disclosure must be a mapping", {})
    prec = disclosure.get("measured_precision")
    _check_number("measured_precision", prec, 0.0, 1.0)
    posture = disclosure.get("posture")
    if not isinstance(posture, str) or not posture.strip():
        raise SchemaError("LI-GATE-002", "disclosure.posture missing/empty", {})
    pinned = (snapshot.manifest.get("measured") or {}).get("precision")
    if pinned is not None and isinstance(pinned, (int, float)) and abs(float(prec) - float(pinned)) > 1e-9:
        raise SchemaError(
            "LI-GATE-002", "disclosed precision disagrees with the PINNED manifest",
            {"disclosed": prec, "pinned": pinned},
        )
    return disclosure


def _event(kind: str, payload: dict, now: datetime | None) -> StoreEvent:
    return StoreEvent(schema_version=1, kind=kind, occurred_at=now or datetime.now(UTC), payload=payload)


def annotate(
    snapshot: PinnedSnapshot,
    ctx: CandidateCtx,
    *,
    flip_probability: float,
    model_family: str,
    latency_s: float,
    disclosure: dict[str, Any],
    prediction_target_tier: str,
    prediction_target_detail: str | None = None,
    now: datetime | None = None,
) -> StoreEvent:
    """The annotated response — subject-bound, disclosure-validated, trace-schema."""
    if not isinstance(model_family, str) or not model_family.strip():
        raise SchemaError("LI-GATE-002", "model_family missing", {})
    if prediction_target_tier not in ("diff_touched", "user_designated"):
        raise SchemaError("LI-GATE-002", "prediction_target_tier unknown (abstain instead)",
                          {"got": prediction_target_tier})
    if not _SHA_RE.fullmatch(ctx.patch_sha256):
        raise SchemaError("LI-GATE-002", "candidate patch hash malformed", {})
    p = _check_number("flip_probability", flip_probability, 0.0, 1.0)
    lat = _check_number("latency_s", latency_s, 0.0, 3600.0)
    disc = _check_disclosure(disclosure, snapshot)
    return _event("gate_annotated", {
        "interface_version": INTERFACE_VERSION,
        "predictor_hash": snapshot.predictor_hash,
        "predictor_version": snapshot.predictor_version,
        "corpus_version": snapshot.corpus_version,
        "candidate": {"repo": ctx.repo, "patch_sha256": ctx.patch_sha256,
                       **({"wire_payload_sha256": ctx.wire_payload_sha256}
                          if ctx.wire_payload_sha256 else {})},
        "rationale_ptr": ctx.rationale_ptr,
        "flip_probability": p,
        "model_family": model_family,
        "latency_s": round(lat, 6),
        "predictor_disclosure": disc,
        "prediction_target_tier": prediction_target_tier,
        "prediction_target_detail": prediction_target_detail,  # the designated set, recorded
    }, now)


def refuse(snapshot: PinnedSnapshot, ctx: CandidateCtx, *, reason: str,
           now: datetime | None = None) -> StoreEvent:
    """The OQ-10 abstention event — silence on purpose, recorded (never a
    fabricated denominator)."""
    if not isinstance(reason, str) or not reason.strip():
        raise SchemaError("LI-GATE-002", "abstention reason required", {})
    return _event("prediction_refused", {
        "interface_version": INTERFACE_VERSION,
        "predictor_hash": snapshot.predictor_hash,
        "corpus_version": snapshot.corpus_version,
        "candidate": {"repo": ctx.repo, "patch_sha256": ctx.patch_sha256},
        "reason": reason,
    }, now)


def timed(fn, *args, **kwargs):
    """Latency instrumentation helper (NFR-P1 path) — returns (result, seconds)."""
    t0 = time.perf_counter()
    res = fn(*args, **kwargs)
    return res, time.perf_counter() - t0
