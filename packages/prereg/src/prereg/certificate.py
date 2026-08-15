"""Threshold certificates — FR-21 blocking authorization as prereg artifacts (Story 7.1).

Pure: stdlib only, zero project imports, zero network (AD-9). The certificate
body is CONTENT-ONLY (AD-7 reproducible class): no wall-clock, no uuid inside
the hashed payload — occurrence metadata (issued_at, anchored_at, anchor_mode)
lives in the ledger rows (prereg.ledger.certificate_entry), and the external
anchor stays an edge/ceremony act.

FR-21 rules encoded here (verbatim semantics, prd.md l.319-326):

- issuance REFUSES a certified precision at or below the registered bar —
  "No configuration permits blocking at or below the bar" (LI-PRERE-002).
  Strictly above is the only issuing regime.
- a supersession is a NEW certificate (direction="superseding") that cites the
  revoked one by content hash plus a reason; the original chain is never
  rewritten (AD-3, erratum-protocol.md). Negative direction carries the same
  artifact discipline (§7).
- every citation binds CONTENT BYTES (sha256, 64-hex), never mutable names:
  the probe verdict artifact, the sealed probe-design package manifest, and
  decision.toml (the registered bar is "by amendment, not by edit").
- confidence scores are never an input; model generations are explicitly named
  (generation-scoped, freshness hook for Story 7.2).
- validation is offline and pure: anyone with the artifacts can re-derive the
  certificate hash and re-check the citations (prereg-ceremony.md promise).

Error registry (story 7.1, LI-PRERE family):
LI-PRERE-001 malformed/missing hash · LI-PRERE-002 precision at/below bar
(issuance refused) · LI-PRERE-003 supersession inconsistency · LI-PRERE-004
empty generations · LI-PRERE-005 non-finite or out-of-range numeric ·
LI-PRERE-006 strict-type violation.
"""

from __future__ import annotations

import json
import math
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from prereg.anchor_format import VerifyReport

_SHA = re.compile(r"[0-9a-f]{64}")
BAR_FORMULA = "cost_regen / (cost_regen + cost_exec)"


class CertificateError(Exception):
    """Typed prereg-certificate failure; serializes {code, message, ctx}."""

    def __init__(self, code: str, message: str, ctx: dict[str, Any] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.ctx = ctx or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "ctx": self.ctx}


@dataclass(frozen=True)
class CertificateCitation:
    """A content binding: artifact location pointer + sha256 of its bytes."""

    artifact: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"artifact": self.artifact, "sha256": self.sha256}


@dataclass(frozen=True)
class BarInstantiation:
    """The Net-Positive Precision Bar instantiated from decision.toml [bar]."""

    formula: str
    cost_exec_usd: float
    cost_regen_usd: float
    registered_bar: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "formula": self.formula,
            "cost_exec_usd": self.cost_exec_usd,
            "cost_regen_usd": self.cost_regen_usd,
            "registered_bar": self.registered_bar,
        }


@dataclass(frozen=True)
class SignerRef:
    """Signer identity declaration (KEYS.md): who + which key fingerprint.

    Key material is provisioned at ceremony time (Story 7.5); CI signs nothing.
    """

    identity: str
    key_fingerprint: str

    def to_dict(self) -> dict[str, str]:
        return {"identity": self.identity, "key_fingerprint": self.key_fingerprint}


@dataclass(frozen=True)
class Certificate:
    """A threshold certificate body — content-only, hash-identified (AD-12)."""

    direction: str                      # "issued" | "superseding"
    verdict_citation: CertificateCitation
    package_citation: CertificateCitation
    decision_citation: CertificateCitation
    generations: tuple[str, ...]
    certified_precision: float          # FRACTION, never percentage points
    precision_wilson95: tuple[float, float]
    bar: BarInstantiation
    signer: SignerRef
    certificate_hash: str
    supersedes: str | None = None
    supersession_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "kind": "threshold-certificate-v1",
            "direction": self.direction,
            "verdict_citation": self.verdict_citation.to_dict(),
            "package_citation": self.package_citation.to_dict(),
            "decision_citation": self.decision_citation.to_dict(),
            "generations": list(self.generations),
            "certified_precision": self.certified_precision,
            "precision_wilson95": list(self.precision_wilson95),
            "bar": self.bar.to_dict(),
            "signer": self.signer.to_dict(),
        }
        if self.supersedes is not None:
            body["supersedes"] = self.supersedes
            body["supersession_reason"] = self.supersession_reason
        return body


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_certificate_hash(body: Mapping[str, Any]) -> str:
    """sha256 of canonical JSON of the body WITHOUT the certificate_hash key."""
    return sha256(_canon({k: v for k, v in body.items() if k != "certificate_hash"}).encode()).hexdigest()


def _is_number(v: Any) -> bool:
    # strict-bool guard (Epic 6 F4): True is NOT a number here
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_number(errors: list[tuple[str, str]], name: str, v: Any, lo: float, hi: float) -> None:
    if not _is_number(v):
        errors.append(("LI-PRERE-006", f"{name} must be numeric (strict bool), got {type(v).__name__}"))
        return
    f = float(v)
    if math.isnan(f) or math.isinf(f) or not (lo <= f <= hi):
        errors.append(("LI-PRERE-005", f"{name} non-finite or outside [{lo},{hi}]: {v!r}"))


def _check_citation(errors: list[tuple[str, str]], name: str, c: Any) -> None:
    if not isinstance(c, Mapping) or set(c) != {"artifact", "sha256"}:
        errors.append(("LI-PRERE-006", f"{name} must be {{artifact, sha256}}, got {c!r:.120}"))
        return
    if not isinstance(c["artifact"], str) or not c["artifact"].strip():
        errors.append(("LI-PRERE-006", f"{name}.artifact must be a non-empty string"))
    h = c["sha256"]
    if not isinstance(h, str) or not _SHA.fullmatch(h):
        errors.append(("LI-PRERE-001", f"{name}.sha256 malformed (need 64-hex): {str(h)[:16]}…"))


def _validate_body(body: Mapping[str, Any]) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    if body.get("kind") != "threshold-certificate-v1":
        errors.append(("LI-PRERE-006", f"unknown certificate kind: {body.get('kind')!r}"))
    direction = body.get("direction")
    if direction not in ("issued", "superseding"):
        errors.append(("LI-PRERE-006", f"direction must be issued|superseding, got {direction!r}"))

    for name in ("verdict_citation", "package_citation", "decision_citation"):
        _check_citation(errors, name, body.get(name))

    generations = body.get("generations")
    if (not isinstance(generations, (list, tuple)) or not generations
            or not all(isinstance(g, str) and g.strip() for g in generations)):
        errors.append(("LI-PRERE-004", f"generations must be a non-empty list of strings, got {generations!r:.120}"))

    _check_number(errors, "certified_precision", body.get("certified_precision"), 0.0, 1.0)
    wilson = body.get("precision_wilson95")
    if not isinstance(wilson, (list, tuple)) or len(wilson) != 2:
        errors.append(("LI-PRERE-006", "precision_wilson95 must be a 2-element interval"))
    else:
        _check_number(errors, "precision_wilson95[0]", wilson[0], 0.0, 1.0)
        _check_number(errors, "precision_wilson95[1]", wilson[1], 0.0, 1.0)
        if (_is_number(wilson[0]) and _is_number(wilson[1])
                and float(wilson[0]) > float(wilson[1])):
            errors.append(("LI-PRERE-005", f"precision_wilson95 inverted: {wilson!r}"))

    bar = body.get("bar")
    if not isinstance(bar, Mapping):
        errors.append(("LI-PRERE-006", f"bar must be a mapping, got {type(bar).__name__}"))
    else:
        if bar.get("formula") != BAR_FORMULA:
            errors.append(("LI-PRERE-006", f"bar.formula must be {BAR_FORMULA!r}"))
        _check_number(errors, "bar.cost_exec_usd", bar.get("cost_exec_usd"), 0.0, 1e6)
        _check_number(errors, "bar.cost_regen_usd", bar.get("cost_regen_usd"), 0.0, 1e6)
        _check_number(errors, "bar.registered_bar", bar.get("registered_bar"), 0.0, 1.0)

    signer = body.get("signer")
    if (not isinstance(signer, Mapping)
            or not isinstance(signer.get("identity"), str) or not signer["identity"].strip()
            or not isinstance(signer.get("key_fingerprint"), str) or not signer["key_fingerprint"].strip()):
        errors.append(("LI-PRERE-006", "signer must carry non-empty identity + key_fingerprint"))

    supersedes = body.get("supersedes")
    reason = body.get("supersession_reason")
    if direction == "superseding":
        if not isinstance(supersedes, str) or not _SHA.fullmatch(supersedes):
            errors.append(("LI-PRERE-003", "superseding certificate must cite supersedes as 64-hex hash"))
        if not isinstance(reason, str) or not reason.strip():
            errors.append(("LI-PRERE-003", "superseding certificate must carry a supersession_reason"))
    elif direction == "issued":
        if supersedes is not None or reason is not None:
            errors.append(("LI-PRERE-003", "issued certificate must not carry supersedes/reason"))

    if direction == "issued" and _is_number(body.get("certified_precision")):
        reg = bar.get("registered_bar") if isinstance(bar, Mapping) else None
        if _is_number(reg) and float(body["certified_precision"]) <= float(reg):
            msg = ("issuance refused: certified precision at or below the registered bar "
                   "(FR-21: blocking strictly above; no configuration permits at/below)")
            errors.append(("LI-PRERE-002", msg))
    return errors


def assemble_certificate(
    *,
    direction: str = "issued",
    verdict_citation: Mapping[str, str],
    package_citation: Mapping[str, str],
    decision_citation: Mapping[str, str],
    generations: tuple[str, ...] | list[str],
    certified_precision: float,
    precision_wilson95: tuple[float, float] | list[float],
    bar: Mapping[str, Any],
    signer: Mapping[str, str],
    supersedes: str | None = None,
    supersession_reason: str | None = None,
) -> Certificate:
    """Fail-closed assembly: validate everything BEFORE building (Epic 6 pattern)."""
    body: dict[str, Any] = {
        "kind": "threshold-certificate-v1",
        "direction": direction,
        "verdict_citation": dict(verdict_citation),
        "package_citation": dict(package_citation),
        "decision_citation": dict(decision_citation),
        "generations": list(generations),
        "certified_precision": certified_precision,
        "precision_wilson95": list(precision_wilson95),
        "bar": dict(bar),
        "signer": dict(signer),
    }
    if supersedes is not None:
        body["supersedes"] = supersedes
    if supersession_reason is not None:
        body["supersession_reason"] = supersession_reason

    errors = _validate_body(body)
    if errors:
        code = errors[0][0]
        raise CertificateError(code, "; ".join(msg for _, msg in errors),
                               {"codes": [c for c, _ in errors]})

    cert_hash = compute_certificate_hash(body)
    return Certificate(
        direction=direction,
        verdict_citation=CertificateCitation(**body["verdict_citation"]),
        package_citation=CertificateCitation(**body["package_citation"]),
        decision_citation=CertificateCitation(**body["decision_citation"]),
        generations=tuple(body["generations"]),
        certified_precision=float(certified_precision),
        precision_wilson95=(float(precision_wilson95[0]), float(precision_wilson95[1])),
        bar=BarInstantiation(
            formula=body["bar"]["formula"],
            cost_exec_usd=float(body["bar"]["cost_exec_usd"]),
            cost_regen_usd=float(body["bar"]["cost_regen_usd"]),
            registered_bar=float(body["bar"]["registered_bar"]),
        ),
        signer=SignerRef(identity=body["signer"]["identity"],
                         key_fingerprint=body["signer"]["key_fingerprint"]),
        certificate_hash=cert_hash,
        supersedes=body.get("supersedes"),
        supersession_reason=body.get("supersession_reason"),
    )


def certificate_from_dict(d: Mapping[str, Any]) -> Certificate:
    """Strict parse of a serialized body; re-derives and binds the hash."""
    errors = _validate_body(d)
    claimed = d.get("certificate_hash")
    if not isinstance(claimed, str) or not _SHA.fullmatch(claimed):
        errors.append(("LI-PRERE-001", f"certificate_hash malformed: {str(claimed)[:16]}…"))
    elif compute_certificate_hash(d) != claimed:
        errors.append(("LI-PRERE-001", "certificate_hash does not match recomputed body hash"))
    if errors:
        code = errors[0][0]
        raise CertificateError(code, "; ".join(msg for _, msg in errors),
                               {"codes": [c for c, _ in errors]})
    return Certificate(
        direction=d["direction"],
        verdict_citation=CertificateCitation(**d["verdict_citation"]),
        package_citation=CertificateCitation(**d["package_citation"]),
        decision_citation=CertificateCitation(**d["decision_citation"]),
        generations=tuple(d["generations"]),
        certified_precision=float(d["certified_precision"]),
        precision_wilson95=(float(d["precision_wilson95"][0]), float(d["precision_wilson95"][1])),
        bar=BarInstantiation(formula=d["bar"]["formula"],
                             cost_exec_usd=float(d["bar"]["cost_exec_usd"]),
                             cost_regen_usd=float(d["bar"]["cost_regen_usd"]),
                             registered_bar=float(d["bar"]["registered_bar"])),
        signer=SignerRef(identity=d["signer"]["identity"],
                         key_fingerprint=d["signer"]["key_fingerprint"]),
        certificate_hash=claimed,
        supersedes=d.get("supersedes"),
        supersession_reason=d.get("supersession_reason"),
    )


def _cite_bytes_sha(errors: list[str], what: str, cited_sha: str, raw: bytes) -> None:
    actual = sha256(raw).hexdigest()
    if actual != cited_sha:
        errors.append(f"{what} bytes disagree with citation: {actual[:12]}… != cited {cited_sha[:12]}…")


def verify_certificate_bytes(
    cert: Mapping[str, Any],
    *,
    verdict_bytes: bytes,
    package_manifest_bytes: bytes,
    decision_bytes: bytes,
) -> VerifyReport:
    """Offline byte-level proof: hash integrity + citation equality. NO network.

    Equality is proved on BYTES, not objects (Epic 6: "pinned" only counts when
    the comparison is over bytes). decision.toml's [bar] table must match the
    certificate's bar verbatim — the bar moves BY AMENDMENT, not by edit.
    """
    errors: list[str] = []
    for code, msg in _validate_body(cert):
        errors.append(f"{code}: {msg}")
    claimed = cert.get("certificate_hash")
    if isinstance(claimed, str) and _SHA.fullmatch(claimed):
        if compute_certificate_hash(cert) != claimed:
            errors.append("certificate_hash does not match recomputed body hash")
    else:
        errors.append("certificate_hash malformed/missing")

    try:
        vc = cert["verdict_citation"]
        pc = cert["package_citation"]
        dc = cert["decision_citation"]
    except (KeyError, TypeError):
        vc = pc = dc = None
    if isinstance(vc, Mapping) and isinstance(vc.get("sha256"), str):
        _cite_bytes_sha(errors, "verdict artifact", vc["sha256"], verdict_bytes)
    if isinstance(pc, Mapping) and isinstance(pc.get("sha256"), str):
        _cite_bytes_sha(errors, "probe package manifest", pc["sha256"], package_manifest_bytes)
    if isinstance(dc, Mapping) and isinstance(dc.get("sha256"), str):
        _cite_bytes_sha(errors, "decision.toml", dc["sha256"], decision_bytes)
        try:
            decision = tomllib.loads(decision_bytes.decode("utf-8"))
            registered = decision.get("bar")
            bar = cert.get("bar")
            if isinstance(bar, Mapping):
                if not isinstance(registered, Mapping):
                    errors.append("decision.toml lacks a [bar] table — the certificate's bar "
                                  "citation cannot be verified (amendment, not edit)")
                else:
                    for key in ("cost_exec_usd", "cost_regen_usd", "registered_bar"):
                        if key not in registered:
                            errors.append(f"decision.toml [bar] lacks {key} — the certificate's "
                                          f"bar citation is incomplete (amendment, not edit)")
                        elif not _is_number(registered[key]):
                            errors.append(f"decision.toml [bar] {key} is not numeric: "
                                          f"{registered[key]!r}")
                        elif _is_number(bar.get(key)) and float(registered[key]) != float(bar[key]):
                            errors.append(
                                f"bar.{key} {bar[key]!r} != decision.toml {registered[key]!r} "
                                "(the bar is cited verbatim — amendment, not edit)")
                    formula = registered.get("net_positive_precision_formula")
                    if not isinstance(formula, str):
                        errors.append("decision.toml [bar] lacks net_positive_precision_formula")
                    elif formula != BAR_FORMULA:
                        errors.append(f"decision.toml formula {formula!r} != canonical "
                                      f"{BAR_FORMULA!r}")
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            errors.append("decision bytes are not parseable TOML")
    return VerifyReport(ok=not errors, errors=tuple(errors))


def currently_valid(
    certificates: Mapping[str, Mapping[str, Any]],
    certificate_hash: str,
    *,
    query_generation: str | None = None,
) -> bool:
    """Pure validity predicate (fail-closed): exists, parses, nobody superseded
    it, and the query generation is inside its named set (FR-21 c2 freshness).

    EVERY entry must parse strictly — one malformed row poisons the whole set
    (fail-closed, Epic 5: optional/lenient loaders are lies).
    """
    if certificate_hash not in certificates:
        return False
    parsed: dict[str, Certificate] = {}
    for h, body in certificates.items():
        try:
            parsed[h] = certificate_from_dict(body)
        except CertificateError:
            return False
    for h, cert in parsed.items():
        if h != certificate_hash and cert.supersedes == certificate_hash:
            return False
    cert = parsed[certificate_hash]
    if query_generation is not None:
        return query_generation in cert.generations
    return True
