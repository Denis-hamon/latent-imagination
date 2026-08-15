"""Per-deployment workload precision check (story 7.2, FR-21 c1): strict-bool
rows, hand-computed measurement, strictly-above-bar, fail-closed policy load,
and the freshness rule that an absent/stale check authorizes nothing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from core_schema.errors import SchemaError
from gate.workload_check import (
    WORKLOAD_CHECK_IFACE_VERSION,
    WorkloadRow,
    authorization_state,
    check_against_bar,
    load_workload_policy,
    measure_workload_precision,
    wilson95_interval,
    workload_checked_event,
)
from pydantic import ValidationError

BAR = 0.8889


def _row(prob: float, outcome: str = "valid_execution",
         tier: str = "diff_touched", **extra) -> WorkloadRow:
    return WorkloadRow(patch_sha256="a" * 64, flip_probability=prob,
                       prediction_target_tier=tier, outcome=outcome, **extra)


class TestWorkloadRowStrictness:
    def test_happy(self):
        r = _row(0.6)
        assert r.flip_probability == 0.6
        assert r.outcome == "valid_execution"

    def test_confidence_is_never_an_input(self):
        """AC4: any extra key — confidence/score — is a validation error."""
        for smuggled in ("confidence", "confidence_tier", "score", "rank"):
            with pytest.raises(ValidationError):
                _row(0.6, **{smuggled: 0.99})

    def test_bool_probability_rejected(self):
        with pytest.raises(ValidationError):
            _row(True)  # strict-bool: True is not 1.0

    def test_nan_inf_rejected(self):
        for bad in (float("nan"), float("inf")):
            with pytest.raises(ValidationError):
                _row(bad)

    def test_bad_sha_and_tier_and_outcome_rejected(self):
        with pytest.raises(ValidationError):
            WorkloadRow(patch_sha256="zzz", flip_probability=0.5,
                        prediction_target_tier="diff_touched",
                        outcome="valid_execution")
        with pytest.raises(ValidationError):
            WorkloadRow(patch_sha256="a" * 64, flip_probability=0.5,
                        prediction_target_tier="invented_tier",
                        outcome="valid_execution")
        with pytest.raises(ValidationError):
            WorkloadRow(patch_sha256="a" * 64, flip_probability=0.5,
                        prediction_target_tier="diff_touched",
                        outcome="some_judge_verdict")  # judge-free: only the 3 outcomes


class TestWilson:
    def test_no_data_no_interval(self):
        assert wilson95_interval(0, 0) == (0.0, 0.0)

    def test_all_and_none(self):
        lo, hi = wilson95_interval(0, 10)
        assert lo == 0.0 and 0.0 < hi < 0.35
        lo, hi = wilson95_interval(10, 10)
        assert hi == 1.0 and lo > 0.65

    def test_hand_computed_midpoint(self):
        # k=5,n=10: phat=0.5, z=1.96 -> center=(0.5+0.192)/1.192=0.5805...,
        # symmetric interval around ~0.5 after clamping math
        lo, hi = wilson95_interval(5, 10)
        assert 0.2 < lo < 0.5 < hi < 0.8
        assert lo < hi

    def test_invalid_counts_closed(self):
        for bad in ((-1, 10), (11, 10), (True, 10)):
            with pytest.raises(SchemaError):
                wilson95_interval(bad[0], bad[1])


class TestMeasurement:
    def test_hand_computed_confusion(self):
        # 3 predicted flips above 0.5; 2 of them are true flips
        rows = [
            _row(0.9, "valid_execution"),                  # tp
            _row(0.8, "valid_execution"),                  # tp
            _row(0.7, "false_start_tests_ran_no_flip"),    # fp
            _row(0.2, "valid_execution"),                  # fn (below thr, but flipped)
            _row(0.1, "false_start_tests_ran_no_flip"),    # tn
        ]
        rep = measure_workload_precision(rows)
        assert (rep.tp, rep.fp, rep.fn, rep.tn) == (2, 1, 1, 1)
        assert rep.n == 5
        assert rep.precision == pytest.approx(2 / 3)
        assert rep.binarization_threshold == 0.5

    def test_infra_failure_counts_as_no_flip(self):
        rep = measure_workload_precision([
            _row(0.9, "false_start_infrastructure_failure"),  # predicted flip, none observed
        ])
        assert (rep.tp, rep.fp) == (0, 1)
        assert rep.precision == pytest.approx(0.0)

    def test_no_positive_predictions_is_none_not_zero(self):
        rep = measure_workload_precision([_row(0.1, "valid_execution"),
                                          _row(0.2, "false_start_tests_ran_no_flip")])
        assert rep.precision is None
        assert rep.precision_wilson95 is None
        assert rep.fn == 1 and rep.tn == 1

    def test_empty_history(self):
        rep = measure_workload_precision([])
        assert rep.n == 0 and rep.precision is None

    def test_strict_binarization_boundary(self):
        # exactly 0.5 is NOT > 0.5 -> negative prediction
        rep = measure_workload_precision([_row(0.5, "valid_execution")])
        assert rep.fn == 1 and rep.tp == 0

    def test_custom_threshold_and_guard(self):
        rep = measure_workload_precision([_row(0.4, "valid_execution")],
                                         binarization_threshold=0.3)
        assert rep.tp == 1
        for bad in (0.0, 1.0, -0.1, 1.1, float("nan"), True):
            with pytest.raises(SchemaError):
                measure_workload_precision([], binarization_threshold=bad)

    def test_tiers_are_recorded(self):
        rep = measure_workload_precision([
            _row(0.9, tier="diff_touched"), _row(0.8, tier="user_designated")])
        assert rep.prediction_target_tiers == ("diff_touched", "user_designated")


class TestCheckAgainstBar:
    def test_strictly_above_enables(self):
        rows = [_row(0.9, "valid_execution")] * 9 + [_row(0.1, "false_start_tests_ran_no_flip")]
        rep = measure_workload_precision(rows)  # precision 1.0 (9/9)
        v = check_against_bar(rep, registered_bar=BAR)
        assert v.blocking_enabled is True
        assert "strictly above" in v.reason

    def test_at_bar_stays_advisory(self):
        # construct precision exactly 8/9 ~ 0.888..., closest honest way:
        # precision equal to bar needs tp/(tp+fp) == 0.8889 -> 8/9
        rows = [_row(0.9, "valid_execution")] * 8 + [_row(0.9, "false_start_tests_ran_no_flip")]
        rep = measure_workload_precision(rows)
        assert rep.precision == pytest.approx(8 / 9)
        v = check_against_bar(rep, registered_bar=8 / 9)
        assert v.blocking_enabled is False
        assert "at/below" in v.reason

    def test_no_positive_predictions_stays_advisory(self):
        rep = measure_workload_precision([_row(0.1, "valid_execution")])
        v = check_against_bar(rep, registered_bar=BAR)
        assert v.blocking_enabled is False
        assert "undefined" in v.reason

    def test_bar_guards(self):
        rep = measure_workload_precision([_row(0.9)])
        for bad in (1.5, -0.1, float("nan"), True):
            with pytest.raises(SchemaError):
                check_against_bar(rep, registered_bar=bad)


class TestPolicyLoad:
    def _write(self, tmp_path, text):
        p = tmp_path / "policy.toml"
        p.write_text(text)
        return p

    def test_happy(self, tmp_path):
        pol = load_workload_policy(self._write(tmp_path,
                                               "[cadence]\nmax_age_days = 14\n"
                                               "[measurement]\nbinarization_threshold = 0.5\n"))
        assert pol.max_age_days == 14
        assert pol.binarization_threshold == 0.5

    @pytest.mark.parametrize("bad", [
        "",  # missing file is separate; empty toml lacks tables
        "[cadence]\nmax_age_days = 14\n",  # missing measurement
        "[cadence]\nmax_age_days = 0\n[measurement]\nbinarization_threshold = 0.5\n",
        "[cadence]\nmax_age_days = -3\n[measurement]\nbinarization_threshold = 0.5\n",
        "[cadence]\nmax_age_days = 14\n[measurement]\nbinarization_threshold = 0.0\n",
        "[cadence]\nmax_age_days = 14\n[measurement]\nbinarization_threshold = 1.0\n",
        "[cadence]\nmax_age_days = 14\n[measurement]\nbinarization_threshold = true\n",
        "not toml [[",
    ])
    def test_fail_closed(self, tmp_path, bad):
        if bad == "":
            with pytest.raises(SchemaError):
                load_workload_policy(tmp_path / "absent.toml")
            return
        with pytest.raises(SchemaError) as ei:
            load_workload_policy(self._write(tmp_path, bad))
        assert ei.value.code == "LI-GATE-008"


class TestFreshness:
    NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    AGE = timedelta(days=14)

    def _row(self, when, enabled, reason="r"):
        return {"kind": "workload_checked", "occurred_at": when,
                "payload": {"blocking_enabled": enabled, "reason": reason}}

    def test_no_check_authorizes_nothing(self):
        v = authorization_state([], max_age=self.AGE, now=self.NOW)
        assert v.blocking_permitted is False
        assert "no workload check" in v.reason

    def test_fresh_positive_permits(self):
        rows = [self._row("2026-08-14T00:00:00Z", True)]
        v = authorization_state(rows, max_age=self.AGE, now=self.NOW)
        assert v.blocking_permitted is True
        assert v.last_checked_at is not None

    def test_stale_check_expires_blocking(self):
        rows = [self._row("2026-07-01T00:00:00Z", True)]
        v = authorization_state(rows, max_age=self.AGE, now=self.NOW)
        assert v.blocking_permitted is False
        assert "expired" in v.reason

    def test_newest_negative_wins_even_if_old_positive_exists(self):
        rows = [self._row("2026-08-10T00:00:00Z", True),
                self._row("2026-08-14T00:00:00Z", False, reason="sub-bar locally")]
        v = authorization_state(rows, max_age=self.AGE, now=self.NOW)
        assert v.blocking_permitted is False
        assert "sub-bar locally" in v.reason

    def test_naive_or_malformed_never_authorize(self):
        assert authorization_state(
            [{"kind": "workload_checked", "occurred_at": "2026-08-14T00:00:00",
              "payload": {"blocking_enabled": True}}],
            max_age=self.AGE, now=self.NOW).blocking_permitted is False
        assert authorization_state(
            [{"kind": "workload_checked", "occurred_at": "2026-08-14T00:00:00Z",
              "payload": {"blocking_enabled": "truthy-string"}}],
            max_age=self.AGE, now=self.NOW).blocking_permitted is False

    def test_non_check_kinds_ignored(self):
        rows = [{"kind": "gate_annotated", "occurred_at": "2026-08-14T00:00:00Z",
                 "payload": {"blocking_enabled": True}}]
        v = authorization_state(rows, max_age=self.AGE, now=self.NOW)
        assert v.blocking_permitted is False


class TestEvent:
    def test_shape_and_strictness(self):
        rep = measure_workload_precision([_row(0.9, "valid_execution")])
        v = check_against_bar(rep, registered_bar=0.5)
        from gate.workload_check import WorkloadPolicy
        ev = workload_checked_event(certificate_hash="b" * 64, generation="gen-x",
                                    report=rep, verdict=v,
                                    policy=WorkloadPolicy(14, 0.5), now=_FIXED_NOW())
        assert ev.kind == "workload_checked"
        assert ev.payload["precision"] == pytest.approx(1.0)
        assert ev.payload["blocking_enabled"] is True
        assert ev.payload["interface_version"] == WORKLOAD_CHECK_IFACE_VERSION
        assert ev.payload["prediction_target_tiers"] == ["diff_touched"]

    def test_guards(self):
        rep = measure_workload_precision([])
        v = check_against_bar(rep, registered_bar=BAR)
        from gate.workload_check import WorkloadPolicy
        pol = WorkloadPolicy(14, 0.5)
        with pytest.raises(SchemaError):
            workload_checked_event(certificate_hash="notahash", generation="g",
                                   report=rep, verdict=v, policy=pol)
        with pytest.raises(SchemaError):
            workload_checked_event(certificate_hash="b" * 64, generation="",
                                   report=rep, verdict=v, policy=pol)


def _FIXED_NOW() -> datetime:
    return datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
