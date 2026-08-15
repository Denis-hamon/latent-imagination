"""Blocking decision path (story 7.3, FR-21/FR-22): the single evaluated
route to a block — budget pre-registered, local check enabled AND strictly
above bar, fresh, denominator-true, flip predicted. Includes the mechanical
FR-21 c4 proof: a seeded sweep asserting NO configuration blocks at/below the
bar, and the end-to-end audit chain trace → certificate → verdict citation."""

from __future__ import annotations

import json
import math
import random
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from gate.blocking import (
    BlockContext,
    FalseBlockBudget,
    LocalCheckState,
    authorize_blocking,
    evaluate_blocking,
    load_false_block_budget,
    patch_blocked_event,
)
from gate.decision_log import append_decision
from gate.testing import make_fixture_certificate, write_certificate_snapshot
from prereg.certificate import CertificateError, compute_certificate_hash

REPO = Path(__file__).resolve().parents[3]
BUDGET_PATH = REPO / "governance" / "gate" / "false-block-budget-v1.toml"
NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
BAR = 0.8889


def _authorize(tmp_path, certified: float = 0.93, generations=("probe-gen-a",),
               query="probe-gen-a"):
    cert = make_fixture_certificate(certified, generations=generations)
    root = tmp_path / "cert-snap"
    pin = write_certificate_snapshot(root, [cert], cert)
    return authorize_blocking(root, expected_certificate_hash=pin, query_generation=query), cert


def _ctx(tmp_path, *, certified=0.93, local_precision=0.95, enabled=None,
         checked_at="2026-08-15T00:00:00Z", budget=True, max_age=14, thr=0.5):
    auth, cert = _authorize(tmp_path, certified)
    if enabled is None:
        enabled = local_precision is not None and local_precision > cert.bar.registered_bar
    budget_obj = load_false_block_budget(BUDGET_PATH) if budget else None
    return BlockContext(certificate=auth,
                        local_check=LocalCheckState(local_precision, checked_at, enabled),
                        budget=budget_obj, max_age_days=max_age,
                        binarization_threshold=thr), cert


class TestBudgetLoader:
    def test_real_registered_budget_loads_and_seals(self):
        b = load_false_block_budget(BUDGET_PATH)
        assert isinstance(b, FalseBlockBudget)
        assert b.max_false_block_rate == pytest.approx(0.05)
        assert b.cost_exec_usd == pytest.approx(0.0025)
        assert b.cost_regen_usd == pytest.approx(0.0200)
        assert b.seal_sha256 == sha256(BUDGET_PATH.read_bytes()).hexdigest()
        assert len(b.seal_sha256) == 64

    def test_seal_is_recorded_in_the_protocol_doc(self):
        """The protocol cites the frozen seal; drift between the registered
        budget bytes and the documented seal is a test failure, not prose."""
        doc = (REPO / "governance" / "gate" / "workload-check-protocol.md").read_text()
        assert load_false_block_budget(BUDGET_PATH).seal_sha256 in doc

    def test_seal_moves_when_bytes_move(self, tmp_path):
        original = load_false_block_budget(BUDGET_PATH).seal_sha256
        # append a trailing comment: still valid TOML, different bytes -> the
        # seal (hash of the exact file bytes) must move. (A byte-flip here would
        # corrupt the closing triple-quote and be caught as LI-GATE-009 instead,
        # which is a different, also-valid failure path.)
        tampered = tmp_path / "budget.toml"
        tampered.write_bytes(BUDGET_PATH.read_bytes() + b"# tamper\n")
        assert load_false_block_budget(tampered).seal_sha256 != original

    def test_fail_closed_variants(self, tmp_path):
        with pytest.raises(SchemaError) as ei:
            load_false_block_budget(tmp_path / "absent.toml")
        assert ei.value.code == "LI-GATE-009"
        bad_docs = [
            "not toml [[",
            "[budget]\nmax_false_block_rate = 0.05\n",           # no derivation
            "[budget]\nmax_false_block_rate = 0.0\n[derivation]\ncost_exec_usd = 1\ncost_regen_usd = 1\n",
            "[budget]\nmax_false_block_rate = 1.0\n[derivation]\ncost_exec_usd = 1\ncost_regen_usd = 1\n",
            "[budget]\nmax_false_block_rate = true\n[derivation]\ncost_exec_usd = 1\ncost_regen_usd = 1\n",
            "[budget]\nmax_false_block_rate = 0.05\n[derivation]\ncost_exec_usd = 0\ncost_regen_usd = 1\n",
            "[budget]\nmax_false_block_rate = 0.05\n[derivation]\ncost_exec_usd = -1\ncost_regen_usd = 1\n",
        ]
        for i, doc in enumerate(bad_docs):
            p = tmp_path / f"b{i}.toml"
            p.write_text(doc)
            with pytest.raises(SchemaError) as ei:
                load_false_block_budget(p)
            assert ei.value.code == "LI-GATE-009"


class TestDecisionLegs:
    def test_all_legs_green_blocks(self, tmp_path):
        ctx, cert = _ctx(tmp_path)
        d = evaluate_blocking(flip_probability=0.9, prediction_target_tier="diff_touched",
                              context=ctx, now=NOW)
        assert d.action == "block"
        assert "blocking authorized" in d.reason
        assert cert.certificate_hash[:12] in d.reason

    def test_no_budget_no_block(self, tmp_path):
        ctx, _ = _ctx(tmp_path, budget=False)
        d = evaluate_blocking(flip_probability=0.9, prediction_target_tier="diff_touched",
                              context=ctx, now=NOW)
        assert d.action == "advise"
        assert "false-block budget" in d.reason

    def test_local_check_disabled_advises(self, tmp_path):
        ctx, _ = _ctx(tmp_path, enabled=False)
        d = evaluate_blocking(flip_probability=0.9, prediction_target_tier="diff_touched",
                              context=ctx, now=NOW)
        assert d.action == "advise"
        assert "did not enable" in d.reason

    def test_enabled_flag_alone_never_trusted(self, tmp_path):
        """Forged/corrupted event: enabled=True but precision at/below bar or
        absent — the cross-check refuses (FR-21 c4 defense in depth)."""
        for lp in (BAR, 0.5, None):
            ctx, _ = _ctx(tmp_path, local_precision=lp, enabled=True)
            d = evaluate_blocking(flip_probability=0.9,
                                  prediction_target_tier="diff_touched",
                                  context=ctx, now=NOW)
            assert d.action == "advise"
            assert "no configuration permits blocking" in d.reason or "absent" in d.reason

    def test_stale_check_lapses_blocking(self, tmp_path):
        stale = (NOW - timedelta(days=20)).isoformat()
        ctx, _ = _ctx(tmp_path, checked_at=stale)
        d = evaluate_blocking(flip_probability=0.9, prediction_target_tier="diff_touched",
                              context=ctx, now=NOW)
        assert d.action == "advise"
        assert "expired" in d.reason

    def test_check_at_exact_max_age_is_still_fresh(self, tmp_path):
        edge = (NOW - timedelta(days=14)).isoformat()
        ctx, _ = _ctx(tmp_path, checked_at=edge)
        d = evaluate_blocking(flip_probability=0.9, prediction_target_tier="diff_touched",
                              context=ctx, now=NOW)
        assert d.action == "block"  # boundary documented: staleness is strictly > max_age

    def test_naive_timestamp_fails_closed(self, tmp_path):
        ctx, _ = _ctx(tmp_path, checked_at="2026-08-15T00:00:00")  # naive
        d = evaluate_blocking(flip_probability=0.9, prediction_target_tier="diff_touched",
                              context=ctx, now=NOW)
        assert d.action == "advise"
        assert "fail-closed" in d.reason

    def test_no_denominator_no_block(self, tmp_path):
        ctx, _ = _ctx(tmp_path)
        for tier in (None, "invented", "auto_guessed"):
            d = evaluate_blocking(flip_probability=0.9, prediction_target_tier=tier,
                                  context=ctx, now=NOW)
            assert d.action == "advise"
            assert "OQ-10" in d.reason

    def test_malformed_or_negative_predictions_advise(self, tmp_path):
        ctx, _ = _ctx(tmp_path)
        for prob in (True, "0.9", float("nan"), float("inf"), -0.1, 1.5, None):
            d = evaluate_blocking(flip_probability=prob,
                                  prediction_target_tier="diff_touched",
                                  context=ctx, now=NOW)
            assert d.action == "advise", f"{prob!r} must not block"

    def test_threshold_is_strict(self, tmp_path):
        ctx, _ = _ctx(tmp_path, thr=0.5)
        at = evaluate_blocking(flip_probability=0.5, prediction_target_tier="diff_touched",
                               context=ctx, now=NOW)
        assert at.action == "advise"
        above = evaluate_blocking(flip_probability=0.51, prediction_target_tier="diff_touched",
                                  context=ctx, now=NOW)
        assert above.action == "block"


class TestPropertySweepNoConfigBlocksBelowBar:
    """AC3 mechanical proof: over a seeded 600-combination sweep, blocking
    occurs IFF every leg is strictly satisfied — including both precision legs
    strictly above the bar."""

    def test_sweep(self, tmp_path):
        rng = random.Random(73)
        checked_choices = ["2026-08-15T00:00:00Z",
                           (NOW - timedelta(days=13)).isoformat(),
                           (NOW - timedelta(days=14)).isoformat(),
                           (NOW - timedelta(days=15)).isoformat(),
                           (NOW - timedelta(days=30)).isoformat(),
                           "not-a-timestamp"]
        evaluated = 0
        for _ in range(1200):
            if evaluated >= 500:
                break
            certified = rng.choice([0.85, BAR, 0.8890, 0.93, 0.97])
            local = rng.choice([None, 0.5, BAR, 0.889, 0.93, 0.99])
            enabled = rng.choice([True, False])
            checked_at = rng.choice(checked_choices)
            tier = rng.choice(["diff_touched", "user_designated", None, "invented"])
            prob = rng.choice([0.0, 0.49, 0.5, 0.51, 0.9, True, "0.9", float("nan")])
            budget = rng.choice([True, False])

            if certified <= BAR:
                # 7.1 doctrine: a sub-bar certificate cannot even be issued
                with pytest.raises(CertificateError) as ei:
                    make_fixture_certificate(certified)
                assert ei.value.code == "LI-PRERE-002"
                continue  # no certificate -> no context -> no block, structurally

            ctx, _ = _ctx(tmp_path, certified=certified, local_precision=local,
                             enabled=enabled, checked_at=checked_at, budget=budget)
            d = evaluate_blocking(flip_probability=prob, prediction_target_tier=tier,
                                  context=ctx, now=NOW)
            evaluated += 1

            def _fresh(ts: str) -> bool:
                try:
                    dt = datetime.fromisoformat(ts)
                except ValueError:
                    return False
                if dt.tzinfo is None:
                    return False
                return NOW - dt <= timedelta(days=14)

            prob_ok = (isinstance(prob, (int, float)) and not isinstance(prob, bool)
                       and 0.0 <= float(prob) <= 1.0 and not math.isnan(float(prob))
                       and float(prob) > 0.5)
            local_ok = (local is not None and not isinstance(local, bool)
                        and local > BAR)
            expected_block = (budget and enabled is True and local_ok
                              and _fresh(checked_at)
                              and tier in ("diff_touched", "user_designated")
                              and prob_ok)
            assert (d.action == "block") == expected_block, (
                f"sweep violation: certified={certified} local={local} enabled={enabled} "
                f"checked_at={checked_at} tier={tier} prob={prob!r} budget={budget} "
                f"-> {d.action} ({d.reason})")
        assert evaluated >= 500


def _green_block(tmp_path):
    """A fully-authorized blocking context: every leg green."""
    ctx, cert = _ctx(tmp_path)
    d = evaluate_blocking(flip_probability=0.9, prediction_target_tier="diff_touched",
                          context=ctx, now=NOW)
    assert d.action == "block"
    return ctx, cert, d


class TestTraceEvent:
    def test_trace_payload_contract(self, tmp_path):
        ctx, cert, d = _green_block(tmp_path)
        ev = patch_blocked_event("owner/repo", "e" * 64, flip_probability=0.9,
                                 prediction_target_tier="diff_touched",
                                 context=ctx, decision=d, now=NOW)
        assert ev.kind == "patch_blocked"
        p = ev.payload
        assert p["candidate"] == {"repo": "owner/repo", "patch_sha256": "e" * 64}
        assert p["prediction"]["flip_probability"] == 0.9
        assert p["prediction"]["binarization_threshold"] == 0.5
        assert p["certificate_hash"] == cert.certificate_hash
        assert p["local_precision_estimate"] == pytest.approx(0.95)
        assert p["registered_bar"] == pytest.approx(BAR)
        ca = p["cost_accounting"]
        assert ca["cost_exec_usd"] == pytest.approx(0.0025)
        assert ca["cost_regen_usd"] == pytest.approx(0.0200)
        assert ca["expected_regen_cost_usd"] == ca["cost_regen_usd"]
        assert ca["budget_seal_sha256"] == sha256(BUDGET_PATH.read_bytes()).hexdigest()
        assert p["budget"]["max_false_block_rate"] == pytest.approx(0.05)

    def test_no_trace_without_a_block(self, tmp_path):
        ctx, _ = _ctx(tmp_path, budget=False)
        d = evaluate_blocking(flip_probability=0.9, prediction_target_tier="diff_touched",
                              context=ctx, now=NOW)
        assert d.action == "advise"
        with pytest.raises(SchemaError):
            patch_blocked_event("o/r", "e" * 64, flip_probability=0.9,
                                prediction_target_tier="diff_touched",
                                context=ctx, decision=d, now=NOW)

    def test_trace_guards(self, tmp_path):
        ctx, _, d = _green_block(tmp_path)
        with pytest.raises(SchemaError):
            patch_blocked_event("o/r", "not-a-sha", flip_probability=0.9,
                                prediction_target_tier="diff_touched",
                                context=ctx, decision=d)
        with pytest.raises(SchemaError):
            patch_blocked_event("", "e" * 64, flip_probability=0.9,
                                prediction_target_tier="diff_touched",
                                context=ctx, decision=d)


class TestEndToEndAuditChain:
    """AC4: a block audits from the trace to the certificate to the verdict
    citation, every hop re-derived offline from bytes."""

    def test_trace_to_certificate_to_verdict(self, tmp_path):
        ctx, _, d = _green_block(tmp_path)
        ev = patch_blocked_event("owner/repo", "e" * 64, flip_probability=0.9,
                                 prediction_target_tier="diff_touched",
                                 context=ctx, decision=d, now=NOW)
        log = tmp_path / "deployer-local" / "decisions.jsonl"  # outside any store root
        append_decision(log, ev)

        rows = [json.loads(l) for l in log.read_text().splitlines()]
        assert len(rows) == 1
        trace = rows[0]["payload"]

        # hop 1: trace -> certificate (content hash identity)
        snap_body = json.loads((tmp_path / "cert-snap" / "certificate.json").read_text())
        assert trace["certificate_hash"] == snap_body["certificate_hash"]
        assert compute_certificate_hash(snap_body) == trace["certificate_hash"]

        # hop 2: certificate -> verdict citation (fixture bytes binding)
        manifest = json.loads((tmp_path / "cert-snap" / "supersession-manifest.json").read_text())
        assert trace["certificate_hash"] in manifest["certificates"]
        cited = manifest["certificates"][trace["certificate_hash"]]["verdict_citation"]
        assert cited["sha256"] == sha256(b"verdict").hexdigest()

        # hop 3: budget seal in the trace matches the registered file bytes
        assert trace["cost_accounting"]["budget_seal_sha256"] == \
            sha256(BUDGET_PATH.read_bytes()).hexdigest()
