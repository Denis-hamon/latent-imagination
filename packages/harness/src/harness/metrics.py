"""ERBVE — Error Rate Before Valid Execution (FR-6). PRD Glossary arithmetic.

Denominator rule (Glossary, binding): per Task, M = every Execution Attempt up to
and INCLUDING the first Valid Execution (by attempt_window.start order). A Task
that never reaches a Valid Execution contributes all its attempts, all False
Starts (rate 1 for that task).

Two aggregations, both reported:
- macro (primary): mean of per-task false-start rates
- micro (pooled): total false starts / total counted attempts
"""

from __future__ import annotations

from dataclasses import dataclass

from core_schema.domain import LabelOutcome

INVALID = object()  # sentinel for "task excluded" (e.g. no labeled attempts)


@dataclass(frozen=True)
class TaskERBVE:
    task_id: str
    attempts_counted: int
    false_starts: int
    rate: float
    reached_valid: bool


@dataclass(frozen=True)
class ERBVEReport:
    per_task: tuple[TaskERBVE, ...]
    macro_rate: float
    micro_rate: float
    total_attempts: int
    total_false_starts: int


def _task_rate(task_id: str, attempts: list[tuple[str, LabelOutcome]]) -> TaskERBVE:
    """attempts: (start_iso, outcome) sorted ascending by start time."""
    first_valid_idx = next(
        (i for i, (_, o) in enumerate(attempts) if o == LabelOutcome.VALID_EXECUTION),
        None,
    )
    counted = attempts if first_valid_idx is None else attempts[: first_valid_idx + 1]
    false = sum(1 for _, o in counted if o != LabelOutcome.VALID_EXECUTION)
    n = len(counted)
    return TaskERBVE(
        task_id=task_id,
        attempts_counted=n,
        false_starts=false,
        rate=(false / n) if n else 0.0,
        reached_valid=first_valid_idx is not None,
    )


def compute_erbve(
    labels: list[dict],
    *,
    task_of_attempt,
    start_of_attempt,
) -> ERBVEReport:
    """labels: iterable of dicts with attempt_id + outcome.
    task_of_attempt / start_of_attempt: resolvers attempt_id → task_id / start ISO.
    """
    by_task: dict[str, list[tuple[str, LabelOutcome]]] = {}
    for lbl in labels:
        aid = lbl["attempt_id"]
        by_task.setdefault(task_of_attempt(aid), []).append(
            (start_of_attempt(aid), LabelOutcome(lbl["outcome"]))
        )
    per_task = tuple(
        _task_rate(tid, sorted(items, key=lambda x: x[0]))
        for tid, items in sorted(by_task.items())
    )
    total_attempts = sum(t.attempts_counted for t in per_task)
    total_false = sum(t.false_starts for t in per_task)
    macro = sum(t.rate for t in per_task) / len(per_task) if per_task else 0.0
    micro = total_false / total_attempts if total_attempts else 0.0
    return ERBVEReport(per_task, macro, micro, total_attempts, total_false)
