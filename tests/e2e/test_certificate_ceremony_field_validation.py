"""Story 7.5 field validation: blocking active ONLY under certificate +
local-check conditions — the integration proof tying 7.1+7.2+7.3+7.4
together. Also drives the ceremony script end-to-end on fixtures."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from gate.blocking import (
    BlockContext,
    LocalCheckState,
    authorize_blocking,
    evaluate_blocking,
    load_false_block_budget,
    patch_blocked_event,
)
from gate.decision_log import append_decision
from gate.shadow import select_for_shadow
from gate.testing import make_fixture_certificate, write_certificate_snapshot
from prereg.certificate import CertificateError

REPO = Path(__file__).resolve().parents[2]
BUDGET_PATH = REPO / "governance" / "gate" / "false-block-budget-v1.toml"

sys.path.insert(0, str(REPO / "scripts" / "prereg"))
import certificate_ceremony as cc

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _cert_and_pin(tmp_path, precision=0.93, generations=("rehearsal-gen-1",)):
    cert = make_fixture_certificate(precision, generations=generations)
    root = tmp_path / "cert-snap"
    pin = write_certificate_snapshot(root, [cert], cert)
    return cert, root, pin


def _ctx(auth, *, local_precision=0.95, enabled=True, checked_at=None,
         budget=True, max_age=14, thr=0.5):
    budget_obj = load_false_block_budget(BUDGET_PATH) if budget else None
    return BlockContext(
        certificate=auth,
        local_check=LocalCheckState(local_precision, checked_at or NOW.isoformat(),
                                    enabled),
        budget=budget_obj, max_age_days=max_age, binarization_threshold=thr)


class TestBlockPath:
    """AC2: blocking IS active when all legs pass."""

    def test_full_chain_blocks_and_traces(self, tmp_path):
        _, root, pin = _cert_and_pin(tmp_path)
        auth = authorize_blocking(root, expected_certificate_hash=pin,
                                  query_generation="rehearsal-gen-1")
        ctx = _ctx(auth)
        d = evaluate_blocking(flip_probability=0.9, prediction_target_tier="diff_touched",
                              context=ctx, now=NOW)
        assert d.action == "block"
        ev = patch_blocked_event("o/r", "e" * 64, flip_probability=0.9,
                                 prediction_target_tier="diff_touched",
                                 context=ctx, decision=d, now=NOW)
        log = tmp_path / "deployer" / "decisions.jsonl"
        append_decision(log, ev)
        rows = [json.loads(l) for l in log.read_text().splitlines()]
        assert rows[0]["kind"] == "patch_blocked"
        assert rows[0]["payload"]["certificate_hash"] == pin

    def test_shadow_sampling_deterministic(self, tmp_path):
        _, _, pin = _cert_and_pin(tmp_path)
        a = select_for_shadow("e" * 64, pin, shadow_rate=0.10)
        b = select_for_shadow("e" * 64, pin, shadow_rate=0.10)
        assert a == b  # reproducible


class TestAdvisePaths:
    """AC2: blocking is NOT active when any leg fails."""

    def test_no_budget(self, tmp_path):
        _, root, pin = _cert_and_pin(tmp_path)
        auth = authorize_blocking(root, expected_certificate_hash=pin,
                                  query_generation="rehearsal-gen-1")
        ctx = _ctx(auth, budget=False)
        assert evaluate_blocking(flip_probability=0.9,
                                 prediction_target_tier="diff_touched",
                                 context=ctx, now=NOW).action == "advise"

    def test_local_below_bar(self, tmp_path):
        _, root, pin = _cert_and_pin(tmp_path)
        auth = authorize_blocking(root, expected_certificate_hash=pin,
                                  query_generation="rehearsal-gen-1")
        ctx = _ctx(auth, local_precision=0.5, enabled=True)
        assert evaluate_blocking(flip_probability=0.9,
                                 prediction_target_tier="diff_touched",
                                 context=ctx, now=NOW).action == "advise"

    def test_stale_check(self, tmp_path):
        _, root, pin = _cert_and_pin(tmp_path)
        auth = authorize_blocking(root, expected_certificate_hash=pin,
                                  query_generation="rehearsal-gen-1")
        ctx = _ctx(auth, checked_at=(NOW - timedelta(days=20)).isoformat())
        assert evaluate_blocking(flip_probability=0.9,
                                 prediction_target_tier="diff_touched",
                                 context=ctx, now=NOW).action == "advise"

    def test_no_denominator(self, tmp_path):
        _, root, pin = _cert_and_pin(tmp_path)
        auth = authorize_blocking(root, expected_certificate_hash=pin,
                                  query_generation="rehearsal-gen-1")
        ctx = _ctx(auth)
        assert evaluate_blocking(flip_probability=0.9,
                                 prediction_target_tier=None,
                                 context=ctx, now=NOW).action == "advise"

    def test_no_flip_predicted(self, tmp_path):
        _, root, pin = _cert_and_pin(tmp_path)
        auth = authorize_blocking(root, expected_certificate_hash=pin,
                                  query_generation="rehearsal-gen-1")
        ctx = _ctx(auth)
        assert evaluate_blocking(flip_probability=0.3,
                                 prediction_target_tier="diff_touched",
                                 context=ctx, now=NOW).action == "advise"

    def test_subbar_certificate_unconstructible(self):
        """7.1 doctrine: a sub-bar certificate cannot even be issued."""
        with pytest.raises(CertificateError) as ei:
            make_fixture_certificate(0.8889)
        assert ei.value.code == "LI-PRERE-002"

    def test_no_certificate_no_block(self, tmp_path):
        """No pin at all → LI-GATE-006, no block."""
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(tmp_path / "empty", expected_certificate_hash="a" * 64)
        assert ei.value.code == "LI-GATE-006"

    def test_generation_outside_certified_set(self, tmp_path):
        _, root, pin = _cert_and_pin(tmp_path)
        with pytest.raises(SchemaError) as ei:
            authorize_blocking(root, expected_certificate_hash=pin,
                                query_generation="wrong-gen")
        assert ei.value.code == "LI-GATE-006"


class TestCeremonyScript:
    """AC1+AC3: the ceremony script runs end-to-end on fixtures."""

    def test_ceremony_pass_and_report(self, tmp_path):
        store = tmp_path / "store"
        report = tmp_path / "report.json"
        out = cc.main(["--store-root", str(store), "--report", str(report)])
        assert out["outcome"] == "PASS"
        r = json.loads(report.read_text())
        assert r["field_validation"]["block_path"]["action"] == "block"
        for leg in ("no_budget", "local_below_bar", "stale_check", "no_denominator",
                    "no_flip"):
            assert r["field_validation"][leg]["action"] == "advise"
        assert "revocation_drill_link" in r
        assert r["release"]["anchor_mode"].startswith("ots-")  # live or simulated

    def test_ceremony_page_has_no_residual_placeholders(self, tmp_path):
        store = tmp_path / "store"
        report = tmp_path / "report.json"
        cc.main(["--store-root", str(store), "--report", str(report)])
        page = (store / "ceremony-packet" / "ceremony-page.md").read_text()
        import re
        unfilled = [p for p in re.findall(r"\{[a-z_]+\}", page) if p != "{placeholder}"]
        assert unfilled == [], f"residual placeholders: {unfilled}"

    def test_ceremony_release_packet_anchored(self, tmp_path):
        store = tmp_path / "store"
        report = tmp_path / "report.json"
        cc.main(["--store-root", str(store), "--report", str(report)])
        assert list((store / "chains").glob("*.json"))
        # proof file is .ots (live) or .sim.ots (simulated) — accept either
        proofs = list((store / "proofs").glob("*.ots"))
        assert proofs, "no proof file found"

    def test_non_empty_store_refused(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        (store / "leftover").write_text("x")
        with pytest.raises(SystemExit, match="non-empty"):
            cc.main(["--store-root", str(store), "--report", str(tmp_path / "r.json")])
