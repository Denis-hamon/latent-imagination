"""Latent Imagination — core schema.

Public surface. Everything downstream (ingest, labeling, harness, probe, gate)
imports domain shapes and identity from here. Identity is derived ONLY in
`core_schema.identity` (AD-12).
"""

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
from core_schema.errors import SchemaError, ensure_aware_utc
from core_schema.events import StoreEvent
from core_schema.identity import (
    attempt_id,
    fingerprint_hash,
    normalize_diff,
    task_fingerprint,
)
from core_schema.trace import (
    AgentRef,
    ExecutionTrace,
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
)

__all__ = [
    "AgentRef",
    "AttemptWindow",
    "CandidatePatch",
    "EnvironmentFingerprint",
    "ExecutionAttempt",
    "ExecutionTrace",
    "FinalMetrics",
    "Label",
    "LabelOutcome",
    "Metrics",
    "Observation",
    "ObservationResult",
    "PatchProvenance",
    "QuarantineReason",
    "QuarantineRecord",
    "RunRecord",
    "SchemaError",
    "Step",
    "StoreEvent",
    "Task",
    "ToolCall",
    "attempt_id",
    "ensure_aware_utc",
    "fingerprint_hash",
    "normalize_diff",
    "task_fingerprint",
]
