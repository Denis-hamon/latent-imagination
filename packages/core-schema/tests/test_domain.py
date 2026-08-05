"""Domain model contracts: shapes, strictness, timezone rule, id derivation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from core_schema.domain import (
    AttemptWindow,
    CandidatePatch,
    EnvironmentFingerprint,
    ExecutionAttempt,
    Label,
    LabelOutcome,
    PatchProvenance,
    QuarantineReason,
    QuarantineRecord,
    RunRecord,
    Task,
)
from core_schema.errors import SchemaError
from pydantic import ValidationError


@pytest.fixture()
def fp() -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        os_family="linux",
        python_version="3.12.8",
        deps_lock_sha256="a" * 64,
    )


@pytest.fixture()
def task() -> Task:
    return Task.from_parts(
        repo_full_name="django/django",
        commit_sha="c" * 40,
        f2p_tests=("tests/a.py::test_x", "tests/b.py::test_y"),
    )


class TestTask:
    def test_task_id_is_content_derived_and_repeatable(self):
        a = Task.from_parts("django/django", "c" * 40, ("t2", "t1"))
        b = Task.from_parts("django/django", "c" * 40, ("t1", "t2", "t1"))
        assert a.task_id == b.task_id  # sorted+unique normalization
        assert a.f2p_tests == ("t1", "t2")

    def test_content_change_changes_id(self):
        a = Task.from_parts("django/django", "c" * 40, ("t1",))
        b = Task.from_parts("django/django", "d" * 40, ("t1",))
        assert a.task_id != b.task_id

    def test_mismatched_explicit_id_rejected(self):
        with pytest.raises(SchemaError) as exc:
            Task(
                repo_full_name="django/django",
                commit_sha="c" * 40,
                f2p_tests=("t1",),
                task_id="wrong",
            )
        assert exc.value.code == "LI-SCHEMA-006"

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            Task.from_parts("django/django", "c" * 40, ("t1",), bogus=1)  # type: ignore[call-arg]


class TestAttemptWindowTZ:
    def test_naive_datetime_rejected_002(self):
        with pytest.raises(SchemaError) as exc:
            AttemptWindow(
                start=datetime(2026, 8, 5, 10, 0, 0),  # noqa: DTZ001 - naive is the tested rejection path
                end=datetime(2026, 8, 5, 10, 1, 0, tzinfo=UTC),
            )
        assert exc.value.code == "LI-SCHEMA-002"

    def test_aware_non_utc_normalized_to_utc(self):
        paris = timezone(timedelta(hours=2))
        w = AttemptWindow(
            start=datetime(2026, 8, 5, 12, 0, 0, tzinfo=paris),
            end=datetime(2026, 8, 5, 12, 5, 0, tzinfo=paris),
        )
        assert w.start == datetime(2026, 8, 5, 10, 0, 0, tzinfo=UTC)
        assert w.start.tzinfo == UTC


class TestLabelsAndQuarantine:
    def test_label_outcomes_exact(self):
        assert set(LabelOutcome) == {
            LabelOutcome.VALID_EXECUTION,
            LabelOutcome.FALSE_START_TESTS_RAN_NO_FLIP,
            LabelOutcome.FALSE_START_INFRASTRUCTURE_FAILURE,
        }

    def test_label_carries_schema_and_ruleset_versions(self):
        lbl = Label(
            attempt_id="a" * 64,
            outcome=LabelOutcome.VALID_EXECUTION,
            schema_version=1,
            ruleset_version="rules-v1",
        )
        assert lbl.ruleset_version == "rules-v1"

    def test_quarantine_reasons_exact(self):
        assert set(QuarantineReason) == {
            QuarantineReason.AMBIGUOUS_OUTPUT,
            QuarantineReason.MISSING_F2P,
            QuarantineReason.ENVIRONMENT_UNDETERMINED,
            QuarantineReason.DUPLICATE_IDENTITY,
        }

    def test_quarantine_record_shape(self):
        q = QuarantineRecord(
            attempt_id="b" * 64,
            reason_code=QuarantineReason.AMBIGUOUS_OUTPUT,
            rule_ids=("R-1", "R-2"),
            trace_ref="blob://traces/1.json",
        )
        assert q.reason_code is QuarantineReason.AMBIGUOUS_OUTPUT


class TestRunRecord:
    def test_uuid7_and_occurrence_only(self):
        r = RunRecord(started_at=datetime(2026, 8, 5, tzinfo=UTC), purpose="smoke")
        assert r.run_id.version == 7

    def test_runrecord_naive_rejected(self):
        with pytest.raises(SchemaError):
            RunRecord(
                started_at=datetime(2026, 8, 5),  # noqa: DTZ001 - naive is the tested rejection path
                purpose="x",
            )


class TestAttemptModel:
    def test_attempt_shape(self, fp, task):
        att = ExecutionAttempt(
            attempt_id="b" * 64,
            task_id=task.task_id,
            patch_hash="d" * 64,
            env_fingerprint=fp,
            attempt_window=AttemptWindow(
                start=datetime(2026, 8, 5, 10, tzinfo=UTC),
                end=datetime(2026, 8, 5, 10, 2, tzinfo=UTC),
            ),
            raw_test_output_ref="blob://out/1.txt",
        )
        assert att.trajectory_ref is None
        patch = CandidatePatch(
            diff_hash="d" * 64,
            provenance=PatchProvenance(
                model_family="claude",
                model_version="sonnet-x",
                scaffold_name="harbor",
                scaffold_version="0.20.0",
            ),
        )
        assert patch.provenance.scaffold_name == "harbor"
