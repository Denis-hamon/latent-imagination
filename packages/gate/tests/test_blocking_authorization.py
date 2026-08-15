"""Blocking authorization seam (story 7.1, FR-21): fail-closed on every axis,
both directions proved behaviorally (deny without a valid certificate, allow
with a pinned above-bar certificate) — the evolved Epic-5 guard contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from gate.blocking import BlockingAuthorization, authorize_blocking, refuse_blocking
from gate.decision_log import append_decision
from gate.testing import (
    certificate_body,
    make_fixture_certificate,
    write_certificate_snapshot,
)


def _make_cert(precision: float = 0.93, *, direction: str = "issued",
               supersedes: str | None = None, reason: str | None = None,
               generations: tuple[str, ...] = ("probe-gen-a",)):
    return make_fixture_certificate(precision, generations=generations,
                                    direction=direction, supersedes=supersedes,
                                    reason=reason)


def _body(cert) -> dict:
    return certificate_body(cert)


def _snapshot(tmp_path: Path, certs: list, candidate) -> tuple[Path, str]:
    """Pinned hand-off (AD-1): certificate.json + supersession-manifest.json.
    The pin is the certificate CONTENT hash (AD-12)."""
    return tmp_path, write_certificate_snapshot(tmp_path, certs, candidate)


class TestDenyPaths:
    """Every refusal is LI-GATE-006 (hard-fail), and the pin is mandatory."""

    def test_missing_certificate_fails_closed(self, tmp_path):
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(tmp_path, expected_certificate_hash="a" * 64)
        assert ei.value.code == "LI-GATE-006"

    def test_pin_shape_enforced(self, tmp_path):
        cert = _make_cert()
        root, _ = _snapshot(tmp_path, [cert], cert)
        for bad in ("zzz", "A" * 64, "", None):
            with pytest.raises(SchemaError) as ei:
                authorize_blocking(root, expected_certificate_hash=bad)
            assert ei.value.code == "LI-GATE-006"

    def test_pin_mismatch_fails(self, tmp_path):
        cert = _make_cert()
        root, _ = _snapshot(tmp_path, [cert], cert)
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(root, expected_certificate_hash="0" * 64)
        assert ei.value.code == "LI-GATE-006"
        assert "mismatch" in ei.value.message

    def test_tampered_body_breaks_the_pin(self, tmp_path):
        cert = _make_cert()
        root, pin = _snapshot(tmp_path, [cert], cert)
        body = json.loads((root / "certificate.json").read_bytes())
        body["certified_precision"] = 0.999  # tamper post-hoc
        (root / "certificate.json").write_text(json.dumps(body))
        with pytest.raises(SchemaError):
            authorize_blocking(root, expected_certificate_hash=pin)

    def test_body_with_forged_internal_hash_fails(self, tmp_path):
        cert = _make_cert()
        root, _ = _snapshot(tmp_path, [cert], cert)
        forged = json.dumps(_body(cert) | {"certificate_hash": "b" * 64})
        (root / "certificate.json").write_text(forged)
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(root, expected_certificate_hash="b" * 64)
        assert ei.value.code == "LI-GATE-006"  # recomputation exposes the forgery

    def test_candidate_absent_from_manifest_fails(self, tmp_path):
        cert, other = _make_cert(), _make_cert(0.94, generations=("probe-gen-b",))
        root, pin = _snapshot(tmp_path, [other], cert)  # manifest lacks the candidate
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(root, expected_certificate_hash=pin)
        assert ei.value.code == "LI-GATE-006"
        assert "absent" in ei.value.message

    def test_manifest_key_body_mismatch_fails(self, tmp_path):
        cert = _make_cert()
        root, pin = _snapshot(tmp_path, [cert], cert)
        man = json.loads((root / "supersession-manifest.json").read_text())
        man["certificates"]["f" * 64] = man["certificates"].pop(cert.certificate_hash)
        (root / "supersession-manifest.json").write_text(json.dumps(man))
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(root, expected_certificate_hash=pin)
        assert ei.value.code == "LI-GATE-006"

    def test_superseded_certificate_hard_fails(self, tmp_path):
        """AC3 core: revocation kills authorization — the downgrade drill."""
        a = _make_cert(0.93)
        b = _make_cert(0.85, direction="superseding", supersedes=a.certificate_hash,
                       reason="re-measurement dropped certified precision to 0.85 <= bar")
        root, pin = _snapshot(tmp_path, [a, b], a)
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(root, expected_certificate_hash=pin)
        assert ei.value.code == "LI-GATE-006"
        assert "superseded" in ei.value.message

    def test_generation_outside_certified_set_keeps_blocking_off(self, tmp_path):
        cert = _make_cert(generations=("probe-gen-a",))
        root, pin = _snapshot(tmp_path, [cert], cert)
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(root, expected_certificate_hash=pin,
                               query_generation="unseen-model-gen")
        assert ei.value.code == "LI-GATE-006"
        assert "re-probe" in ei.value.message

    def test_below_bar_certificate_never_authorizes(self, tmp_path):
        """A superseding certificate may RECORD below-bar precision (downgrade)
        but can never authorize blocking (FR-21 strictly-above)."""
        a = _make_cert(0.93)
        b = _make_cert(0.85, direction="superseding", supersedes=a.certificate_hash,
                       reason="downgrade")
        root, pin = _snapshot(tmp_path, [a, b], b)
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(root, expected_certificate_hash=pin)
        assert ei.value.code == "LI-GATE-006"
        assert "at/below" in ei.value.message

    def test_exactly_at_bar_never_authorizes(self, tmp_path):
        """Strictness boundary: == bar is NOT above bar."""
        a = _make_cert(0.93)
        at_bar = _make_cert(0.8889, direction="superseding", supersedes=a.certificate_hash,
                            reason="re-measurement landed exactly on the bar")
        root, pin = _snapshot(tmp_path, [a, at_bar], at_bar)
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(root, expected_certificate_hash=pin)
        assert ei.value.code == "LI-GATE-006"

    def test_empty_manifest_fails_closed(self, tmp_path):
        cert = _make_cert()
        root, pin = _snapshot(tmp_path, [cert], cert)
        (root / "supersession-manifest.json").write_text('{"certificates": {}}')
        with pytest.raises(SchemaError):
            authorize_blocking(root, expected_certificate_hash=pin)


class TestAllowPath:
    def test_valid_above_bar_certificate_authorizes(self, tmp_path):
        cert = _make_cert(0.93, generations=("probe-gen-a", "probe-gen-b"))
        root, pin = _snapshot(tmp_path, [cert], cert)
        auth = authorize_blocking(root, expected_certificate_hash=pin)
        assert isinstance(auth, BlockingAuthorization)
        assert pin == cert.certificate_hash
        assert auth.certificate_hash == cert.certificate_hash
        assert auth.certified_precision == pytest.approx(0.93)
        assert auth.registered_bar == pytest.approx(0.8889)
        assert auth.generations == ("probe-gen-a", "probe-gen-b")

    def test_generation_query_inside_scope_authorizes(self, tmp_path):
        cert = _make_cert(0.93, generations=("probe-gen-a", "probe-gen-b"))
        root, pin = _snapshot(tmp_path, [cert], cert)
        auth = authorize_blocking(root, expected_certificate_hash=pin,
                                  query_generation="probe-gen-b")
        assert auth.certificate_hash == cert.certificate_hash

    def test_superseding_upgrade_authorizes_most_recent(self, tmp_path):
        """Re-probe crosses higher: the superseding cert is the valid one."""
        a = _make_cert(0.90)
        c = _make_cert(0.95, direction="superseding", supersedes=a.certificate_hash,
                       reason="re-probe measured higher precision")
        root, pin = _snapshot(tmp_path, [a, c], c)
        auth = authorize_blocking(root, expected_certificate_hash=pin)
        assert auth.certified_precision == pytest.approx(0.95)


class TestLoggedRefusal:
    """AC3 '(logged)': every hard-fail pairs with a blocking_refused event in
    the deployer-local decision log — never a silent refusal."""

    def test_refuse_blocking_event_shape(self):
        ev = refuse_blocking("certificate superseded", certificate_hint="ab" * 32)
        assert ev.kind == "blocking_refused"
        assert ev.payload["reason"] == "certificate superseded"
        assert ev.payload["interface_version"] == "blocking-authz-v1"
        assert "flip_probability" not in ev.payload

    def test_refusal_requires_reason(self):
        with pytest.raises(SchemaError):
            refuse_blocking("")

    def test_hard_fail_round_trip_is_logged(self, tmp_path):
        a = _make_cert(0.93)
        b = _make_cert(0.85, direction="superseding", supersedes=a.certificate_hash,
                       reason="downgrade")
        root, pin = _snapshot(tmp_path, [a, b], a)
        log = tmp_path / "deployer-local" / "decisions.jsonl"
        try:
            authorize_blocking(root, expected_certificate_hash=pin)
            raise AssertionError("expected LI-GATE-006 hard-fail")
        except SchemaError as exc:
            append_decision(log, refuse_blocking(exc.message, certificate_hint=pin))
        lines = [json.loads(l) for l in log.read_text().splitlines()]
        assert len(lines) == 1
        assert lines[0]["kind"] == "blocking_refused"
        assert "superseded" in lines[0]["payload"]["reason"]
