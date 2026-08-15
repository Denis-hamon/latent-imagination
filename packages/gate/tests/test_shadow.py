"""Shadow-mode sampling + SM-C1 (story 7.4, FR-22 c3): deterministic
reproducible sampler, false-block semantics, budget comparison with the honest
None-rate rule, and the fail-closed policy loader."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from gate.shadow import (
    ShadowPolicy,
    compare_against_budget,
    compute_sm_c1,
    load_shadow_policy,
    make_twin,
    select_for_shadow,
)

REPO = Path(__file__).resolve().parents[3]
POLICY_PATH = REPO / "governance" / "gate" / "shadow-sampling-policy-v1.toml"

CERT = sha256(b"fixture-cert").hexdigest()
PATCH = sha256(b"fixture-patch").hexdigest()


class TestSampler:
    def test_deterministic_and_reproducible(self):
        a = select_for_shadow(PATCH, CERT, shadow_rate=0.5, salt="s")
        for _ in range(5):
            assert select_for_shadow(PATCH, CERT, shadow_rate=0.5, salt="s") == a

    def test_rate_one_samples_everything(self):
        for i in range(20):
            p = sha256(f"p{i}".encode()).hexdigest()
            assert select_for_shadow(p, CERT, shadow_rate=1.0) is True

    def test_salt_changes_membership(self):
        base = {sha256(f"p{i}".encode()).hexdigest() for i in range(200)}
        m1 = {p for p in base if select_for_shadow(p, CERT, shadow_rate=0.5, salt="salt-a")}
        m2 = {p for p in base if select_for_shadow(p, CERT, shadow_rate=0.5, salt="salt-b")}
        assert m1 != m2  # supersession/salt rotation intentionally re-rolls the sample

    def test_certificate_supersession_re_rolls_the_sample(self):
        other_cert = sha256(b"superseding-cert").hexdigest()
        base = [sha256(f"p{i}".encode()).hexdigest() for i in range(200)]
        m1 = {p for p in base if select_for_shadow(p, CERT, shadow_rate=0.5)}
        m2 = {p for p in base if select_for_shadow(p, other_cert, shadow_rate=0.5)}
        assert m1 != m2

    def test_empirical_coverage_tracks_the_rate(self):
        """Mechanism check (not a precision claim): over many synthetic
        identities the sampled share sits near the registered rate."""
        ids = [(sha256(f"patch-{i}".encode()).hexdigest(),
                sha256(f"cert-{i % 7}".encode()).hexdigest()) for i in range(2000)]
        for rate in (0.10, 0.50):
            share = sum(select_for_shadow(p, c, shadow_rate=rate) for p, c in ids) / len(ids)
            assert abs(share - rate) < 0.05, f"rate {rate} drifted to {share}"

    def test_guards_fail_closed(self):
        for bad_patch in ("zzz", "g" * 64, "", None):
            with pytest.raises(SchemaError) as ei:
                select_for_shadow(bad_patch, CERT, shadow_rate=0.5)
            assert ei.value.code == "LI-GATE-010"
        for bad_cert in ("short", PATCH.upper()):
            with pytest.raises(SchemaError):
                select_for_shadow(PATCH, bad_cert, shadow_rate=0.5)
        for bad_rate in (0.0, -0.1, 1.5, float("nan"), True, "0.5"):
            with pytest.raises(SchemaError) as ei:
                select_for_shadow(PATCH, CERT, shadow_rate=bad_rate)
            assert ei.value.code == "LI-GATE-010"


class TestPolicyLoader:
    def test_registered_policy_loads(self):
        pol = load_shadow_policy(POLICY_PATH)
        assert isinstance(pol, ShadowPolicy)
        assert pol.shadow_rate == pytest.approx(0.10)
        assert pol.salt == "shadow-v1"

    def test_fail_closed_variants(self, tmp_path):
        with pytest.raises(SchemaError) as ei:
            load_shadow_policy(tmp_path / "absent.toml")
        assert ei.value.code == "LI-GATE-010"
        for doc in ("not toml [[",
                    "[other]\nx = 1",
                    "[sampling]\nshadow_rate = 0.0\n",
                    "[sampling]\nshadow_rate = 1.5\n",
                    "[sampling]\nshadow_rate = true\n"):
            p = tmp_path / "p.toml"
            p.write_text(doc)
            with pytest.raises(SchemaError) as ei:
                load_shadow_policy(p)
            assert ei.value.code == "LI-GATE-010"


class TestTwinsAndSM:
    def test_make_twin_rejects_non_labelfree_outcomes(self):
        make_twin(PATCH, CERT, "valid_execution")  # the 3 legal outcomes pass
        for bad in ("judge_said_yes", "", None, "VALID_EXECUTION"):
            with pytest.raises(SchemaError):
                make_twin(PATCH, CERT, bad)

    def test_false_block_semantics(self):
        assert make_twin(PATCH, CERT, "valid_execution").is_false_block is True
        assert make_twin(PATCH, CERT, "false_start_tests_ran_no_flip").is_false_block is False
        assert make_twin(PATCH, CERT, "false_start_infrastructure_failure").is_false_block is False

    def test_hand_computed_sm_c1(self):
        twins = [make_twin(sha256(f"p{i}".encode()).hexdigest(), CERT,
                           "valid_execution" if i == 0 else "false_start_tests_ran_no_flip")
                 for i in range(3)]
        rep = compute_sm_c1(twins, n_block_decisions=30)
        assert rep.n_sampled == 3 and rep.n_false_block == 1
        assert rep.false_block_rate == pytest.approx(1 / 3)
        assert rep.sampled_share == pytest.approx(0.1)
        lo, hi = rep.false_block_wilson95
        assert 0.0 < lo < 1 / 3 < hi <= 1.0

    def test_empty_shadow_is_honest_none(self):
        rep = compute_sm_c1([], n_block_decisions=10)
        assert rep.false_block_rate is None
        assert rep.false_block_wilson95 is None
        assert rep.sampled_share == pytest.approx(0.0)
        rep0 = compute_sm_c1([], n_block_decisions=0)
        assert rep0.sampled_share is None  # no denominator, no invention

    def test_negative_denominator_refused(self):
        with pytest.raises(SchemaError):
            compute_sm_c1([], n_block_decisions=-1)

    def test_more_twins_than_decisions_refused(self):
        twins = [make_twin(sha256(f"p{i}".encode()).hexdigest(), CERT, "valid_execution")
                 for i in range(3)]
        with pytest.raises(SchemaError) as ei:
            compute_sm_c1(twins, n_block_decisions=2)
        assert ei.value.code == "LI-GATE-010"


class TestBudgetComparison:
    def _rep(self, rate):
        twins = []
        if rate is not None:
            n = 40
            k = round(rate * n)
            for i in range(n):
                twins.append(make_twin(sha256(f"p{i}".encode()).hexdigest(), CERT,
                                       "valid_execution" if i < k
                                       else "false_start_tests_ran_no_flip"))
        return compute_sm_c1(twins, n_block_decisions=400)

    def test_at_budget_is_within(self):
        v = compare_against_budget(self._rep(0.025), max_false_block_rate=0.05)
        assert v.within_budget is True
        assert "within" in v.reason

    def test_over_budget_is_flagged(self):
        v = compare_against_budget(self._rep(0.10), max_false_block_rate=0.05)
        assert v.within_budget is False
        assert "OVER" in v.reason

    def test_undefined_rate_is_not_compliance(self):
        v = compare_against_budget(self._rep(None), max_false_block_rate=0.05)
        assert v.within_budget is False
        assert "undefined" in v.reason

    def test_budget_guards(self):
        rep = self._rep(0.025)
        for bad in (0.0, 1.0, -0.1, float("nan"), True):
            with pytest.raises(SchemaError):
                compare_against_budget(rep, max_false_block_rate=bad)
