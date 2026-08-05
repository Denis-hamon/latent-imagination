"""ERBVE — Error Rate Before Valid Execution (FR-6). PRD Glossary arithmetic.

Denominator rule (Glossary, binding): per Task, M = every Execution Attempt up to
and INCLUDING the first Valid Execution (ordered by attempt start INSTANT —
starts are parsed to datetimes so mixed offsets sort by real time).

Hardened (review 2026-08-05):
- duplicate attempt_ids are a data-invariant failure, never double-counted
- an empty/all-quarantined input reports `None` rates (no-data ≠ 0.0)
- never-valid tasks contribute rate 1.0 (all attempts are False Starts)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core_schema.domain import LabelOutcome


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
    macro_rate: float | None  # None == no data
    micro_rate: float | None
    total_attempts: int
    total_false_starts: int
    excluded_tasks: tuple[str, ...]  # tasks with zero labeled attempts


def _parse_start(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        raise ValueError(f"naive attempt start: {iso}")
    return dt


def _task_rate(task_id: str, attempts: list[tuple[str, LabelOutcome]]) -> TaskERBVE:
    # sort by real instant; stable order for exact ties (input order preserved)
    ordered = sorted(attempts, key=lambda x: _parse_start(x[0]))
    first_valid_idx = next(
        (i for i, (_, o) in enumerate(ordered) if o == LabelOutcome.VALID_EXECUTION),
        None,
    )
    counted = ordered if first_valid_idx is None else ordered[: first_valid_idx + 1]
    false = sum(1 for _, o in counted if o != LabelOutcome.VALID_EXECUTION)
    n = len(counted)
    return TaskERBVE(
        task_id=task_id,
        attempts_counted=n,
        false_starts=false,
        rate=(false / n) if n else 0.0,
        reached_valid=first_valid_idx is not None,
    )


def compute_erbve(labels: list[dict], *, task_of_attempt, start_of_attempt) -> ERBVEReport:
    """labels: rows {attempt_id, outcome}; resolvers map attempt_id → task/start."""
    seen: set[str] = set()
    dupes: set[str] = set()
    by_task: dict[str, list[tuple[str, LabelOutcome]]] = {}
    for lbl in labels:
        aid = lbl["attempt_id"]
        if aid in seen:
            dupes.add(aid)
            continue  # one attempt counted once; surface the anomaly loudly
        seen.add(aid)
        by_task.setdefault(task_of_attempt(aid), []).append(
            (start_of_attempt(aid), LabelOutcome(lbl["outcome"]))
        )
    if dupes:
        raise ValueError(f"duplicate attempt ids in label set: {sorted(dupes)[:5]} (data invariant)")

    per_task = tuple(
        _task_rate(tid, items) for tid, items in sorted(by_task.items())
    )
    total_attempts = sum(t.attempts_counted for t in per_task)
    total_false = sum(t.false_starts for t in per_task)
    if not per_task or total_attempts == 0:
        return ERBVEReport(per_task, None, None, 0, 0, ())
    macro = sum(t.rate for t in per_task) / len(per_task)
    micro = total_false / total_attempts
    return ERBVEReport(per_task, macro, micro, total_attempts, total_false, ())
