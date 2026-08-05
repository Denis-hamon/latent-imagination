"""Domain models: Task, CandidatePatch, ExecutionAttempt, Label, QuarantineRecord, RunRecord.

Closed shapes (extra="forbid"): schema evolution goes through deliberate version
policy, never through tolerated drift. Timezone rule: aware non-UTC is normalized
to UTC; naive raises LI-SCHEMA-002. Identity is content-derived (AD-12, see
`core_schema.identity`).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core_schema.errors import SchemaError, ensure_aware_utc


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnvironmentFingerprint(StrictModel):
    """Everything about an executor environment that could change outcomes."""

    os_family: str
    python_version: str
    container_image_digest: str | None = None
    deps_lock_sha256: str
    runner_version: str | None = None


class Task(StrictModel):
    """A real OSS Python repo state + its designated fail-to-pass tests."""

    task_id: str  # sha256-derived (AD-12); see Task.from_parts / identity.task_fingerprint
    repo_full_name: str
    commit_sha: str
    f2p_tests: tuple[str, ...]

    @field_validator("f2p_tests")
    @classmethod
    def _sorted_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(v)))

    @model_validator(mode="after")
    def _id_matches_content(self) -> Task:
        from core_schema.identity import task_fingerprint

        expected = task_fingerprint(self.repo_full_name, self.commit_sha, self.f2p_tests)
        if self.task_id != expected:
            raise SchemaError(
                "LI-SCHEMA-006",
                "task_id does not match content-derived value",
                {"given": self.task_id, "expected": expected},
            )
        return self

    @classmethod
    def from_parts(
        cls,
        repo_full_name: str,
        commit_sha: str,
        f2p_tests: tuple[str, ...] | list[str],
        **kwargs: Any,
    ) -> Task:
        from core_schema.identity import task_fingerprint

        tests = tuple(sorted(set(f2p_tests)))
        return cls(
            task_id=task_fingerprint(repo_full_name, commit_sha, tests),
            repo_full_name=repo_full_name,
            commit_sha=commit_sha,
            f2p_tests=tests,
            **kwargs,
        )


class PatchProvenance(StrictModel):
    model_family: str
    model_version: str
    scaffold_name: str
    scaffold_version: str


class CandidatePatch(StrictModel):
    diff_hash: str  # sha256 of the normalized diff (identity.normalize_diff)
    diff_text_ref: str | None = None  # blob store / file reference; the patch itself never inlined here
    provenance: PatchProvenance


class AttemptWindow(StrictModel):
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return ensure_aware_utc(v, "attempt_window")

    @model_validator(mode="after")
    def _ordered(self) -> AttemptWindow:
        if self.end < self.start:
            raise SchemaError(
                "LI-SCHEMA-006",
                "attempt_window.end before start",
                {"start": self.start.isoformat(), "end": self.end.isoformat()},
            )
        return self


class ExecutionAttempt(StrictModel):
    """One run of a Candidate Patch in the Task's environment."""

    attempt_id: str  # identity.attempt_id(...)
    task_id: str
    patch_hash: str
    env_fingerprint: EnvironmentFingerprint
    attempt_window: AttemptWindow
    raw_test_output_ref: str
    trajectory_ref: str | None = None


class LabelOutcome(str, Enum):
    VALID_EXECUTION = "valid_execution"
    FALSE_START_TESTS_RAN_NO_FLIP = "false_start_tests_ran_no_flip"
    FALSE_START_INFRASTRUCTURE_FAILURE = "false_start_infrastructure_failure"


class Label(StrictModel):
    """Per-attempt outcome record; carries the (schema, ruleset) pair it was
    produced under so any label-set stays derivable (FR-3)."""

    attempt_id: str
    outcome: LabelOutcome
    schema_version: int
    ruleset_version: str
    evidence_ref: str | None = None


class QuarantineReason(str, Enum):
    AMBIGUOUS_OUTPUT = "ambiguous_output"
    MISSING_F2P = "missing_f2p"
    ENVIRONMENT_UNDETERMINED = "environment_undetermined"
    DUPLICATE_IDENTITY = "duplicate_identity"


class QuarantineRecord(StrictModel):
    """Attempt held out of Both numerator and denominator (FR-3). Never a Label."""

    attempt_id: str
    reason_code: QuarantineReason
    rule_ids: tuple[str, ...]
    trace_ref: str


class RunRecord(StrictModel):
    """Operational/occurrence artifact — the ONLY model allowed a uuid (AD-7/AD-12)."""

    run_id: UUID = Field(default_factory=uuid7)
    started_at: datetime
    purpose: str

    @field_validator("started_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return ensure_aware_utc(v, "started_at")

    @classmethod
    def open(cls, purpose: str) -> RunRecord:
        # uuid7 minting lives here and only here.
        from datetime import UTC

        return cls(started_at=datetime.now(UTC), purpose=purpose)
