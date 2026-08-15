"""Blocking-mode authorization seam (story 7.1; FR-21, FR-22).

Advisory remains the DEFAULT (FR-19): ``intercept.annotate`` is unchanged and
cannot halt anything. This module is the ONLY blocking seam in the package and
it can only REFUSE to authorize: blocking is permitted strictly when the
caller pins a byte-verified, currently-valid certificate whose certified
precision is STRICTLY above the registered bar (FR-21 c1/c4). Every refusal is
coded LI-GATE-006 and pairs with a ``blocking_refused`` decision-log event —
a logged refusal, never silence (Epic 5 posture).

Pinned hand-off (AD-1): the snapshot directory must carry ``certificate.json``
(the candidate body incl. its ``certificate_hash``) and
``supersession-manifest.json`` (``{"certificates": {<hash>: <body>}}``), copied
OUT of the store. The pin is the certificate's CONTENT hash (AD-12) and is
MANDATORY — an unpinned call is refused (Epic 5: an optional pin is not a
pin). Each file is read once and its parsed body re-derives the hash (the pin
is checked against a recomputation, never against a caller-supplied string).

Confidence scores are never an input anywhere in this path (FR-21).

Story 7.3 adds the blocking DECISION PATH in this same module (the single
allowlisted blocking surface): ``evaluate_blocking`` turns (certificate
authorization + local workload check + prediction + budget) into a
block/advise decision, and ``patch_blocked_event`` emits the auditable trace
(Trace Schema envelope, deployer-local decision log — AD-4: the gate never
writes a canonical store). FR-22 c1 is mechanical here: without a loaded,
pre-registered false-block budget there is NO path to a block. The budget
file (``governance/gate/false-block-budget-v1.toml``) is cited by its sha256
seal in every trace.

Error registry: LI-GATE-006 (authorization refusals, 7.1) · LI-GATE-009
(false-block budget load failures, 7.3).
"""

from __future__ import annotations

import json
import math
import re
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from core_schema.errors import SchemaError
from core_schema.events import StoreEvent
from prereg.certificate import (
    Certificate,
    CertificateError,
    certificate_from_dict,
    currently_valid,
)

BLOCKING_IFACE_VERSION = "blocking-authz-v1"
DECISION_IFACE_VERSION = "blocking-decision-v1"

__all__ = [
    "BLOCKING_IFACE_VERSION",
    "DECISION_IFACE_VERSION",
    "BlockContext",
    "BlockDecision",
    "BlockingAuthorization",
    "FalseBlockBudget",
    "LocalCheckState",
    "authorize_blocking",
    "evaluate_blocking",
    "load_false_block_budget",
    "patch_blocked_event",
    "refuse_blocking",
]


@dataclass(frozen=True)
class BlockingAuthorization:
    """Proof that blocking MAY engage for the certified generations — the
    caller's deployment checks (story 7.2) still gate on their own workload."""

    certificate_hash: str
    certified_precision: float
    registered_bar: float
    generations: tuple[str, ...]


def _load_json_bytes(root: Path, name: str) -> tuple[bytes, dict[str, Any]]:
    path = root / name
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SchemaError("LI-GATE-006", f"blocking authz: {name} unreadable",
                          {"path": str(path), "err": type(exc).__name__}) from exc
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-GATE-006", f"blocking authz: {name} unparseable",
                          {"path": str(path)}) from exc
    if not isinstance(obj, dict):
        raise SchemaError("LI-GATE-006", f"blocking authz: {name} not a mapping",
                          {"path": str(path)})
    return raw, obj


def authorize_blocking(
    snapshot_root: Path,
    *,
    expected_certificate_hash: str,
    query_generation: str | None = None,
) -> BlockingAuthorization:
    """Fail-closed authorization. Raises LI-GATE-006 on ANY invalid state.

    Order of checks is the audit trail: pin shape → pin bytes → body integrity
    → manifest integrity + currency → generation freshness → strictly-above-bar.
    """
    if not isinstance(expected_certificate_hash, str) or not re.fullmatch(r"[0-9a-f]{64}",
                                                                          expected_certificate_hash):
        raise SchemaError("LI-GATE-006",
                          "certificate pin must be 64-hex (mandatory — an optional pin is not a pin)",
                          {"got": expected_certificate_hash})
    root = Path(snapshot_root)
    _, cert_obj = _load_json_bytes(root, "certificate.json")
    try:
        # from_dict recomputes the body hash and binds it (byte-level proof,
        # never a caller-supplied string comparison)
        cert: Certificate = certificate_from_dict(cert_obj)
    except CertificateError as exc:
        raise SchemaError("LI-GATE-006",
                          f"certificate body invalid ({exc.code}): {exc.message}", exc.ctx) from exc
    if cert.certificate_hash != expected_certificate_hash:
        raise SchemaError("LI-GATE-006",
                          "certificate pin mismatch — the pin is the whole point",
                          {"expected": expected_certificate_hash,
                           "actual": cert.certificate_hash})

    _, manifest_obj = _load_json_bytes(root, "supersession-manifest.json")
    certs = manifest_obj.get("certificates")
    if not isinstance(certs, dict) or not certs:
        raise SchemaError("LI-GATE-006",
                          "supersession-manifest.json must carry a non-empty 'certificates' mapping",
                          {"got": type(certs).__name__})
    for key, body in certs.items():
        if not isinstance(body, dict) or body.get("certificate_hash") != key:
            raise SchemaError("LI-GATE-006",
                              "supersession manifest entry integrity: key must equal the body's certificate_hash",
                              {"key": key})
    if expected_certificate_hash not in certs:
        raise SchemaError("LI-GATE-006", "pinned certificate absent from supersession manifest", {})
    if not currently_valid(certs, expected_certificate_hash):
        raise SchemaError("LI-GATE-006",
                          "certificate is superseded (or the manifest failed strict validation) — "
                          "blocking hard-fails on anything but a currently-valid certificate",
                          {"certificate_hash": expected_certificate_hash})
    if query_generation is not None and query_generation not in cert.generations:
        raise SchemaError("LI-GATE-006",
                          "generation outside the certified set — blocking off until re-probe (FR-21 freshness)",
                          {"query_generation": query_generation, "certified": list(cert.generations)})
    if not cert.certified_precision > cert.bar.registered_bar:
        raise SchemaError("LI-GATE-006",
                          "certified precision at/below the registered bar — no configuration "
                          "permits blocking here (FR-21 strictly-above)",
                          {"certified_precision": cert.certified_precision,
                           "registered_bar": cert.bar.registered_bar})
    return BlockingAuthorization(
        certificate_hash=cert.certificate_hash,
        certified_precision=cert.certified_precision,
        registered_bar=cert.bar.registered_bar,
        generations=cert.generations,
    )


def refuse_blocking(reason: str, *, certificate_hint: str | None = None,
                    now: datetime | None = None) -> StoreEvent:
    """The logged refusal — first-class, like prediction_refused (Epic 5)."""
    if not isinstance(reason, str) or not reason.strip():
        raise SchemaError("LI-GATE-006", "blocking-refusal reason required", {})
    payload: dict[str, Any] = {"interface_version": BLOCKING_IFACE_VERSION, "reason": reason}
    if certificate_hint is not None:
        payload["certificate_hint"] = certificate_hint
    return StoreEvent(schema_version=1, kind="blocking_refused",
                      occurred_at=now or datetime.now(UTC), payload=payload)


# ---------------------------------------------------------------------------
# Story 7.3 — the blocking decision path (single allowlisted blocking surface)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FalseBlockBudget:
    """Pre-registered false-block budget + derivation inputs (FR-22 c1).

    ``seal_sha256`` is the hash of the budget file's exact bytes at load time;
    every block trace cites it, so a budget edit without amendment moves the
    seal and breaks the chain (erratum-protocol discipline)."""

    max_false_block_rate: float
    cost_exec_usd: float
    cost_regen_usd: float
    seal_sha256: str


@dataclass(frozen=True)
class LocalCheckState:
    """The deployer's latest workload-check outcome (story 7.2 event payload)."""

    precision: float | None
    checked_at: str          # ISO-8601 tz-aware
    blocking_enabled: bool   # strict bool; nothing else authorizes


@dataclass(frozen=True)
class BlockContext:
    """All legs a block requires, composed fail-closed at construction.

    Cannot be built without a valid 7.1 ``BlockingAuthorization``. ``budget``
    None is a first-class state: it means "no pre-registered budget" and can
    never produce a block (FR-22 c1, mechanically)."""

    certificate: BlockingAuthorization
    local_check: LocalCheckState
    budget: FalseBlockBudget | None
    max_age_days: int
    binarization_threshold: float

    def __post_init__(self) -> None:
        if not isinstance(self.certificate, BlockingAuthorization):
            raise SchemaError("LI-GATE-006",
                              "BlockContext requires a valid BlockingAuthorization", {})
        if not isinstance(self.local_check, LocalCheckState):
            raise SchemaError("LI-GATE-006", "BlockContext requires a LocalCheckState", {})
        if isinstance(self.local_check.blocking_enabled, bool) is False:
            raise SchemaError("LI-GATE-006", "local_check.blocking_enabled must be strict bool", {})
        if isinstance(self.max_age_days, bool) or not isinstance(self.max_age_days, int) \
                or self.max_age_days <= 0:
            raise SchemaError("LI-GATE-006", "max_age_days must be a positive integer",
                              {"got": self.max_age_days})
        thr = self.binarization_threshold
        if isinstance(thr, bool) or not isinstance(thr, (int, float)) \
                or math.isnan(thr) or math.isinf(thr) or not 0.0 < float(thr) < 1.0:
            raise SchemaError("LI-GATE-006",
                              "binarization_threshold must lie strictly inside (0,1)", {"got": thr})


@dataclass(frozen=True)
class BlockDecision:
    action: Literal["block", "advise"]
    reason: str


def load_false_block_budget(path: Path) -> FalseBlockBudget:
    """Fail-closed budget load (LI-GATE-009). No defaults, ever."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise SchemaError("LI-GATE-009", f"false-block budget unreadable: {p}",
                          {"err": type(exc).__name__}) from exc
    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-GATE-009", "false-block budget is not parseable TOML",
                          {"path": str(p)}) from exc
    budget = doc.get("budget")
    derivation = doc.get("derivation")
    if not isinstance(budget, dict) or not isinstance(derivation, dict):
        raise SchemaError("LI-GATE-009",
                          "false-block budget must carry [budget] and [derivation] tables", {})

    def _positive(name: str, table: dict) -> float:
        v = table.get(name)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise SchemaError("LI-GATE-009", f"{name} must be numeric (strict bool)", {"got": v})
        f = float(v)
        if math.isnan(f) or math.isinf(f) or not f > 0.0:
            raise SchemaError("LI-GATE-009", f"{name} must be finite and > 0", {"got": v})
        return f

    rate = budget.get("max_false_block_rate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        raise SchemaError("LI-GATE-009", "budget.max_false_block_rate must be numeric (strict bool)",
                          {"got": rate})
    rf = float(rate)
    if math.isnan(rf) or math.isinf(rf) or not 0.0 < rf < 1.0:
        raise SchemaError("LI-GATE-009",
                          "budget.max_false_block_rate must lie strictly inside (0,1)", {"got": rate})
    return FalseBlockBudget(
        max_false_block_rate=rf,
        cost_exec_usd=_positive("cost_exec_usd", derivation),
        cost_regen_usd=_positive("cost_regen_usd", derivation),
        seal_sha256=sha256(raw).hexdigest(),
    )


def _parse_checked_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return None if dt.tzinfo is None else dt


def evaluate_blocking(
    *,
    flip_probability: Any,
    prediction_target_tier: Any,
    context: BlockContext,
    now: datetime,
) -> BlockDecision:
    """The one evaluated route to a block. Leg order = the audit trail.

    Every advise leg names itself. Block requires: budget pre-registered →
    local check strictly enabled → check fresh → denominator tier valid
    (OQ-10) → flip predicted above the SAME pre-registered threshold the
    workload check used (strict >). The certificate legs (valid, generation in
    scope, strictly above bar) are already enforced by authorize_blocking and
    pinned inside context.certificate — the property test proves no path
    around them exists.
    """
    if context.budget is None:
        return BlockDecision("advise",
                             "no pre-registered false-block budget — FR-22: the budget is "
                             "registered before any blocking ships, so advisory stays on")
    if context.local_check.blocking_enabled is not True:
        return BlockDecision("advise",
                             "local workload check did not enable blocking (at/below-bar or "
                             "no positive predictions) — advisory stays on, reason in the check record")
    # Defense in depth (FR-21 c4): the enabled flag alone is never trusted —
    # the recorded local precision must ITSELF be strictly above the bar
    # (a forged/corrupted event with enabled=True and sub-bar precision
    # authorizes nothing).
    lp = context.local_check.precision
    if isinstance(lp, bool) or not isinstance(lp, (int, float)) \
            or math.isnan(lp) or not lp > context.certificate.registered_bar:
        return BlockDecision("advise",
                             "local precision absent or at/below the registered bar — no "
                             "configuration permits blocking here (FR-21 strictly-above)")
    checked = _parse_checked_at(context.local_check.checked_at)
    if checked is None:
        return BlockDecision("advise",
                             "workload-check timestamp missing/naive/unparseable — fail-closed, "
                             "an unverifiable check authorizes nothing")
    if now - checked > timedelta(days=context.max_age_days):
        return BlockDecision("advise",
                             f"workload check expired ({context.local_check.checked_at} older than "
                             f"{context.max_age_days}d policy) — blocking lapses until re-run")
    if prediction_target_tier not in ("diff_touched", "user_designated"):
        return BlockDecision("advise",
                             "no test-set denominator for this candidate (OQ-10) — no block "
                             "without one, abstention recorded instead")
    if isinstance(flip_probability, bool) or not isinstance(flip_probability, (int, float)):
        return BlockDecision("advise",
                             "flip_probability missing or not strictly numeric — no block on "
                             "malformed prediction input")
    p = float(flip_probability)
    if math.isnan(p) or math.isinf(p) or not 0.0 <= p <= 1.0:
        return BlockDecision("advise", "flip_probability outside [0,1] — no block")
    if not p > context.binarization_threshold:
        return BlockDecision("advise",
                             f"no flip predicted (p={p:.4f} <= threshold "
                             f"{context.binarization_threshold:g}) — advisory")
    return BlockDecision(
        "block",
        f"blocking authorized: certificate {context.certificate.certificate_hash[:12]}…, "
        f"local precision {context.local_check.precision:.4f} strictly above bar "
        f"{context.certificate.registered_bar:.4f}, flip predicted at p={p:.4f}")


def patch_blocked_event(
    candidate_repo: str,
    candidate_patch_sha256: str,
    *,
    flip_probability: float,
    prediction_target_tier: str,
    context: BlockContext,
    decision: BlockDecision,
    now: datetime | None = None,
) -> StoreEvent:
    """The auditable block trace (FR-22 c2): prediction, certificate id, local
    precision estimate, and the regeneration-cost receipt with the budget seal.

    Emitted to the deployer-local decision log (AD-4 fence: never a canonical
    store). The cost accounting QUOTES the budget's derivation inputs — it
    never recomputes from live prices (no oracle, no network).
    """
    if decision.action != "block":
        raise SchemaError("LI-GATE-006",
                          "patch_blocked_event requires a block decision — advise paths "
                          "use the existing annotation/refusal events", {"action": decision.action})
    if context.budget is None:  # defense in depth: evaluate_blocking already refuses
        raise SchemaError("LI-GATE-006", "a block trace cannot exist without a budget", {})
    if not isinstance(candidate_repo, str) or not candidate_repo.strip():
        raise SchemaError("LI-GATE-006", "candidate repo required for the trace", {})
    if not re.fullmatch(r"[0-9a-f]{64}", candidate_patch_sha256):
        raise SchemaError("LI-GATE-006", "candidate patch hash must be 64-hex", {})
    payload: dict[str, Any] = {
        "interface_version": DECISION_IFACE_VERSION,
        "candidate": {"repo": candidate_repo, "patch_sha256": candidate_patch_sha256},
        "prediction": {
            "flip_probability": flip_probability,
            "prediction_target_tier": prediction_target_tier,
            "binarization_threshold": context.binarization_threshold,
        },
        "certificate_hash": context.certificate.certificate_hash,
        "local_precision_estimate": context.local_check.precision,
        "registered_bar": context.certificate.registered_bar,
        "cost_accounting": {
            "cost_exec_usd": context.budget.cost_exec_usd,
            "cost_regen_usd": context.budget.cost_regen_usd,
            "expected_regen_cost_usd": context.budget.cost_regen_usd,
            "budget_seal_sha256": context.budget.seal_sha256,
        },
        "budget": {"max_false_block_rate": context.budget.max_false_block_rate,
                   "seal_sha256": context.budget.seal_sha256},
        "reason": decision.reason,
    }
    return StoreEvent(schema_version=1, kind="patch_blocked",
                      occurred_at=now or datetime.now(UTC), payload=payload)
