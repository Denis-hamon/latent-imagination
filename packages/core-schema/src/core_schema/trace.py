"""ATIF v1.7 trace mirror (adapter-facing shape).

We mirror ATIF's field names exactly for our own Trace Schema; project-specific
payload rides exclusively in sanctioned ``extra`` dicts (trajectory / agent /
step / tool_call / observation_result levels). No new top-level fields, ever —
that is the drift-protection contract with FR-2 and the corpus phase.

Business rules enforced (validator parity with ATIF where applicable):
- step ids sequential starting at 1                      → LI-SCHEMA-005
- agent-only fields on non-agent steps                   → LI-SCHEMA-003
- observation results referencing unknown tool_call_ids  → LI-SCHEMA-004
- naive timestamps                                        → LI-SCHEMA-002
- closed models except the sanctioned ``extra`` slots
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core_schema.errors import SchemaError, ensure_aware_utc

Extra = dict[str, Any]

AGENT_ONLY_FIELDS = ("model_name", "reasoning_content", "llm_call_count")


class _AtifBase(BaseModel):
    """Actions like ATIF: closed schema with a single sanctioned extra slot."""

    model_config = ConfigDict(extra="forbid")

    extra: Extra = Field(default_factory=dict)


class AgentRef(_AtifBase):
    name: str
    version: str | None = None
    model_name: str | None = None
    tool_definitions: list[dict[str, Any]] | None = None  # ATIF v1.5


class ToolCall(_AtifBase):
    tool_call_id: str
    function_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ObservationResult(_AtifBase):
    source_call_id: str | None = None
    content: str
    # content parts (ATIF v1.6 multimodal) are ADDITIVE later: new field,
    # never a type change of ``content`` — see core-schema README version policy.


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[ObservationResult]


class Metrics(_AtifBase):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    cost_usd: float | None = None
    logprobs: list[float] | None = None


class FinalMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_prompt_tokens: int | None = None
    total_completion_tokens: int | None = None
    total_cached_tokens: int | None = None
    total_cost_usd: float | None = None
    total_steps: int | None = None


class Step(_AtifBase):
    step_id: int
    timestamp: datetime
    source: Literal["user", "agent", "system"]
    message: str | None = None
    reasoning_content: str | None = None
    model_name: str | None = None
    llm_call_count: int | None = None  # ATIF v1.7
    tool_calls: list[ToolCall] | None = None
    observation: Observation | None = None
    metrics: Metrics | None = None

    @field_validator("timestamp")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return ensure_aware_utc(v, "step.timestamp")

    @model_validator(mode="after")
    def _agent_only(self) -> Step:
        if self.source != "agent":
            present = [f for f in AGENT_ONLY_FIELDS if getattr(self, f) is not None]
            if present:
                raise SchemaError(
                    "LI-SCHEMA-003",
                    f"agent-only fields on {self.source} step",
                    {"fields": present, "step_id": self.step_id},
                )
        return self


class ExecutionTrace(_AtifBase):
    """One complete agent session on one Task (ATIF v1.7 shape)."""

    schema_version: Literal["ATIF-v1.7"]
    session_id: str
    agent: AgentRef
    steps: list[Step]
    final_metrics: FinalMetrics | None = None

    @model_validator(mode="after")
    def _step_ids(self) -> ExecutionTrace:
        ids = [s.step_id for s in self.steps]
        if ids != list(range(1, len(ids) + 1)):
            raise SchemaError(
                "LI-SCHEMA-005",
                "step_id sequence must start at 1 and be sequential",
                {"got": ids},
            )
        return self

    def validate_business_rules(self) -> None:
        known_call_ids = {
            tc.tool_call_id
            for s in self.steps
            for tc in (s.tool_calls or [])
        }
        for s in self.steps:
            if s.observation:
                for r in s.observation.results:
                    if r.source_call_id and r.source_call_id not in known_call_ids:
                        raise SchemaError(
                            "LI-SCHEMA-004",
                            "observation references unknown tool_call_id",
                            {"step_id": s.step_id, "source_call_id": r.source_call_id},
                        )
