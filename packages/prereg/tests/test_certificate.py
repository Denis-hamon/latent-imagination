"""Threshold certificates (story 7.1): assembly doctrine, byte proofs,
supersession, ledger rows. Hermetic fixtures only — never the real store."""

from __future__ import annotations

import json
from hashlib import sha256

import pytest
from prereg.anchor_format import AnchorRecord, VerifyReport
from prereg.certificate import (
    BAR_FORMULA,
    CertificateError,
    assemble_certificate,
    certificate_from_dict,
    compute_certificate_hash,
    currently_valid,
    verify_certificate_bytes,
)
from prereg.chain import verify_chain_precedence
from prereg.ledger import append_entry, certificate_entry

VERDICT_BYTES = b"# REHEARSAL fixture verdict: matched precision 0.93, above bar 0.8889 (NOT the Act I verdict)\n"
PACKAGE_BYTES = b'{"package": "probe-design", "package_hash": "fixture-only"}\n'
DECISION_BYTES = (
    b'[bar]\n'
    b'cost_exec_usd = 0.0025\n'
    b'cost_regen_usd = 0.0200\n'
    b'net_positive_precision_formula = "cost_regen / (cost_regen + cost_exec)"\n'
    b'registered_bar = 0.8889\n'
)
BAR = {"formula": BAR_FORMULA, "cost_exec_usd": 0.0025,
       "cost_regen_usd": 0.0200, "registered_bar": 0.8889}
SIGNER = {"identity": "fixture-builder", "key_fingerprint": "ab" * 32}
CITATIONS = None  # built per-call below (hash bound to the exact bytes)


def _cit(raw: bytes) -> dict:
    return {"artifact": "fixture://probe-design", "sha256": sha256(raw).hexdigest()}


def _cert(precision: float = 0.93, **kw):
    kw.setdefault("verdict_citation", _cit(VERDICT_BYTES))
    kw.setdefault("package_citation", _cit(PACKAGE_BYTES))
    kw.setdefault("decision_citation", _cit(DECISION_BYTES))
    kw.setdefault("generations", ("rehearsal-gen-1",))
    kw.setdefault("precision_wilson95", (round(max(precision - 0.05, 0.0), 4), round(min(precision + 0.03, 1.0), 4)))
    kw.setdefault("bar", dict(BAR))
    kw.setdefault("signer", dict(SIGNER))
    return assemble_certificate(certified_precision=precision, **kw)


class TestAssembly:
    def test_happy_path_content_only_and_deterministic(self):
        a, b = _cert(), _cert()
        assert a.certificate_hash == b.certificate_hash
        assert len(a.certificate_hash) == 64
        d = a.to_dict()
        assert d["kind"] == "threshold-certificate-v1"
        # AD-7: no occurrence metadata in the hashed body
        for banned in ("created_at", "issued_at", "anchored_at", "uuid"):
            assert banned not in json.dumps(d)
        assert d["certified_precision"] == 0.93
        assert d["generations"] == ["rehearsal-gen-1"]
        assert "supersedes" not in d  # absent for direction=issued

    def test_round_trip_from_dict_binds_hash(self):
        a = _cert()
        back = certificate_from_dict(a.to_dict() | {"certificate_hash": a.certificate_hash})
        assert back == a

    def test_serialized_body_hash_matches(self):
        a = _cert()
        body = a.to_dict() | {"certificate_hash": a.certificate_hash}
        assert compute_certificate_hash(body) == a.certificate_hash


class TestIssuanceDoctrine:
    """FR-21 c4: no configuration permits issuing at or below the bar."""

    def test_exactly_at_bar_refused(self):
        with pytest.raises(CertificateError) as ei:
            _cert(precision=0.8889)
        assert ei.value.code == "LI-PRERE-002"

    def test_epsilon_above_bar_accepted(self):
        cert = _cert(precision=0.88891)
        assert cert.certified_precision == pytest.approx(0.88891)

    @pytest.mark.parametrize("precision", [0.0, 0.3, 0.5, 0.6271, 0.8, 0.8888])
    def test_sweep_below_bar_always_refused(self, precision):
        with pytest.raises(CertificateError) as ei:
            _cert(precision=precision)
        assert ei.value.code == "LI-PRERE-002"

    @pytest.mark.parametrize("precision", [0.889, 0.93, 0.99, 1.0])
    def test_sweep_above_bar_always_accepted(self, precision):
        assert _cert(precision=precision).certificate_hash

    def test_superseding_may_record_below_bar_precision(self):
        """The downgrade case (FR-21 c3): a superseding certificate RECORDS the
        re-measurement; it does not authorize blocking (gate re-checks the bar)."""
        a = _cert()
        b = _cert(precision=0.85, direction="superseding",
                  supersedes=a.certificate_hash,
                  supersession_reason="re-measurement dropped to 0.85 <= bar")
        assert b.direction == "superseding"


class TestStrictValidation:
    def test_malformed_citation_hash(self):
        with pytest.raises(CertificateError) as ei:
            _cert(verdict_citation={"artifact": "x", "sha256": "nothex"})
        assert ei.value.code == "LI-PRERE-001"

    def test_nan_and_inf_refused(self):
        for bad in (float("nan"), float("inf")):
            with pytest.raises(CertificateError) as ei:
                _cert(precision=bad)
            assert ei.value.code == "LI-PRERE-005"

    def test_bool_is_not_a_number(self):
        with pytest.raises(CertificateError) as ei:
            _cert(precision=True)  # strict-bool: True is NOT 1.0 here (Epic 6 F4)
        assert ei.value.code == "LI-PRERE-006"

    def test_empty_generations(self):
        with pytest.raises(CertificateError) as ei:
            _cert(generations=())
        assert ei.value.code == "LI-PRERE-004"

    def test_inverted_wilson_interval(self):
        with pytest.raises(CertificateError) as ei:
            _cert(precision_wilson95=(0.99, 0.90))
        assert ei.value.code == "LI-PRERE-005"

    def test_wrong_bar_formula(self):
        with pytest.raises(CertificateError) as ei:
            _cert(bar=dict(BAR, formula="cost_exec / cost_regen"))
        assert ei.value.code == "LI-PRERE-006"

    def test_superseding_without_supersedes_or_reason(self):
        a = _cert()
        with pytest.raises(CertificateError) as ei:
            _cert(direction="superseding", supersession_reason="r")
        assert ei.value.code == "LI-PRERE-003"
        with pytest.raises(CertificateError) as ei:
            _cert(direction="superseding", supersedes=a.certificate_hash)
        assert ei.value.code == "LI-PRERE-003"

    def test_issued_carries_no_supersession(self):
        with pytest.raises(CertificateError) as ei:
            _cert(supersedes="c" * 64)
        assert ei.value.code == "LI-PRERE-003"


class TestVerifyBytes:
    def _args(self):
        return {"verdict_bytes": VERDICT_BYTES, "package_manifest_bytes": PACKAGE_BYTES,
                "decision_bytes": DECISION_BYTES}

    def _body(self, cert):
        return cert.to_dict() | {"certificate_hash": cert.certificate_hash}

    def test_ok(self):
        rep = verify_certificate_bytes(self._body(_cert()), **self._args())
        assert isinstance(rep, VerifyReport)
        assert rep.ok, rep.errors

    @pytest.mark.parametrize("field", ["verdict_bytes", "package_manifest_bytes", "decision_bytes"])
    def test_one_flipped_byte_breaks_each_citation(self, field):
        args = self._args()
        raw = args[field]
        args[field] = bytes([raw[0] ^ 1]) + raw[1:]
        rep = verify_certificate_bytes(self._body(_cert()), **args)
        assert not rep.ok
        assert any("citation" in e or "bytes disagree" in e for e in rep.errors)

    def test_body_tamper_detected(self):
        body = self._body(_cert())
        body["certified_precision"] = 0.99  # tamper, keep claimed hash
        rep = verify_certificate_bytes(body, **self._args())
        assert not rep.ok
        assert any("does not match recomputed" in e for e in rep.errors)

    def test_bar_must_match_decision_toml_verbatim(self):
        # locally consistent (0.95 > 0.9) but decision.toml says 0.8889
        cert = _cert(precision=0.95, bar=dict(BAR, registered_bar=0.9))
        rep = verify_certificate_bytes(self._body(cert), **self._args())
        assert not rep.ok
        assert any("registered_bar" in e and "amendment" in e for e in rep.errors)


class TestSupersession:
    def _set(self, *certs):
        return {c.certificate_hash: c.to_dict() | {"certificate_hash": c.certificate_hash}
                for c in certs}

    def test_revocation_drill_core(self):
        """AC4 drill: re-measurement drops to <= bar -> downgrade supersedes."""
        a = _cert(precision=0.93)
        b = _cert(precision=0.85, direction="superseding",
                  supersedes=a.certificate_hash,
                  supersession_reason="rehearsal re-measurement dropped certified "
                                      "precision to 0.85 <= bar 0.8889 (downgrade)")
        certs = self._set(a, b)
        assert currently_valid(certs, a.certificate_hash) is False
        assert currently_valid(certs, b.certificate_hash) is True

    def test_chain_most_recent_wins(self):
        a = _cert(precision=0.93)
        b = _cert(precision=0.85, direction="superseding", supersedes=a.certificate_hash,
                  supersession_reason="downgrade")
        c = _cert(precision=0.95, direction="superseding", supersedes=b.certificate_hash,
                  supersession_reason="re-probe crossed the bar again")
        certs = self._set(a, b, c)
        assert currently_valid(certs, a.certificate_hash) is False
        assert currently_valid(certs, b.certificate_hash) is False
        assert currently_valid(certs, c.certificate_hash) is True

    def test_unknown_hash_and_empty_set(self):
        assert currently_valid({}, "d" * 64) is False
        assert currently_valid(self._set(_cert()), "e" * 64) is False

    def test_one_malformed_entry_poisons_the_set_fail_closed(self):
        a = _cert()
        certs = self._set(a)
        certs["f" * 64] = {"kind": "garbage"}
        assert currently_valid(certs, a.certificate_hash) is False

    def test_generation_membership_freshness_hook(self):
        a = _cert()
        certs = self._set(a)
        assert currently_valid(certs, a.certificate_hash, query_generation="rehearsal-gen-1") is True
        assert currently_valid(certs, a.certificate_hash, query_generation="some-other-gen") is False


class TestLedgerRows:
    def test_certificate_row_shape_and_append(self, tmp_path):
        a = _cert()
        row = certificate_entry(
            a.certificate_hash, "issued", a.verdict_citation.sha256,
            list(a.generations), a.certified_precision, a.bar.registered_bar,
            "2026-08-15T10:00:00Z", "2026-08-15T10:01:00Z",
            anchor_mode="ots-simulated (rehearsal)", proof_ref="proofs/x.sim.ots",
            purpose="rehearsal drill fixture")
        assert row["type"] == "certificate"
        assert "supersedes" not in row
        ledger = tmp_path / "prereg-ledger.jsonl"
        append_entry(ledger, row)
        b = _cert(precision=0.85, direction="superseding", supersedes=a.certificate_hash,
                  supersession_reason="downgrade")
        row_b = certificate_entry(
            b.certificate_hash, "superseding", b.verdict_citation.sha256,
            list(b.generations), b.certified_precision, b.bar.registered_bar,
            "2026-08-15T11:00:00Z", "2026-08-15T11:01:00Z",
            anchor_mode="ots-simulated (rehearsal)", proof_ref="proofs/y.sim.ots",
            purpose="rehearsal revocation drill",
            supersedes=a.certificate_hash,
            supersession_reason="downgrade")
        append_entry(ledger, row_b)
        lines = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
        assert len(lines) == 2  # append-only: both rows present, nothing edited
        assert lines[1]["supersedes"] == a.certificate_hash

    def test_precedence_ignores_certificate_rows(self, tmp_path):
        """verify_chain_precedence stays backward-compatible: certificate rows
        are not labels/runs anchors and must not disturb the check."""
        ledger = tmp_path / "prereg-ledger.jsonl"
        entries = [
            {"type": "anchor", "chain_hash": "x" * 64, "ruleset_hash": "e" * 64,
             "anchored_at": "2026-08-04T10:00:00Z", "ots_proof_ref": "p.ots"},
            {"type": "run", "run_id": "run-1", "started_at": "2026-08-05T10:00:00Z",
             "ruleset_hash": "e" * 64, "store_version": "s" * 64},
            certificate_entry("d" * 64, "issued", "v" * 64, ["g"], 0.93, 0.8889,
                              "2026-08-15T10:00:00Z", "2026-08-15T10:01:00Z",
                              anchor_mode="ots-simulated", proof_ref="p", purpose="t"),
        ]
        for e in entries:
            append_entry(ledger, e)
        man = {"artifact_type": "labels", "inputs": {"run_id": "run-1"}, "files": []}
        assert verify_chain_precedence(ledger, [man]).status == "ok"


class TestOfflineAnchorPathUnchanged:
    """The certificate rides the EXISTING anchor contract (1-4): occurrence
    record + OTS stamping digest sha256(raw chain bytes). Nothing new here —
    the test pins that certificate hashes are valid inputs for it."""

    def test_certificate_hash_is_anchorable_like_a_chain_hash(self):
        from prereg.verify import verify_offline

        cert = _cert()
        rec = AnchorRecord(chain_hash=cert.certificate_hash,
                           ots_proof_ref="proofs/cert.sim.ots",
                           anchored_at="2026-08-15T10:01:00Z")
        # verify_offline compares hash strings; the certificate hash must be a
        # drop-in 64-hex input for the established ceremony mechanics.
        from prereg.chain import ChainManifest
        man = ChainManifest(release=cert.certificate_hash, bundle="b" * 64,
                            snapshot="s" * 64, ruleset="e" * 64,
                            code_commit="c" * 40, chain_hash=cert.certificate_hash)
        assert verify_offline(man, rec).ok
