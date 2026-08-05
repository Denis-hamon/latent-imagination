"""Act I campaign driver: batched, resumable, cap-respecting execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


def plan_fingerprint(tasks: list[dict[str, Any]], batch_size: int) -> str:
    canon = json.dumps(
        {"tasks": tasks, "batch_size": batch_size}, sort_keys=True, separators=(",", ":")
    )
    return sha256(canon.encode()).hexdigest()


@dataclass(frozen=True)
class Batch:
    index: int
    tasks: list[dict[str, Any]]
    est_cost_usd: float


def plan_batches(tasks: list[dict[str, Any]], batch_size: int, cost_per_task_usd: float) -> list[Batch]:
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    return [
        Batch(i // batch_size, tasks[i : i + batch_size], cost_per_task_usd * min(batch_size, len(tasks) - i))
        for i in range(0, len(tasks), batch_size)
    ]


@dataclass
class CampaignState:
    done_batches: list[int]
    spent_usd: float
    coverage_gaps: list[dict[str, str]]


def resume_state(progress_path: Path, plan_fingerprint_now: str) -> CampaignState:
    """Resume from progress; REFUSES to silently resume over a plan change:
    a plan drift invalidates the recorded done_batches (coverage integrity)."""
    if not progress_path.exists():
        return CampaignState([], 0.0, [])
    data = json.loads(progress_path.read_text())
    recorded_fp = data.get("plan_fingerprint")
    if recorded_fp and recorded_fp != plan_fingerprint_now:
        raise PlanDriftError(
            "task plan changed since last run — refuse to resume on stale done_batches "
            "(recorded plan differs from current plan)"
        )
    return CampaignState(
        done_batches=data["done_batches"],
        spent_usd=data["spent_usd"],
        coverage_gaps=data.get("coverage_gaps", []),
    )


class PlanDriftError(Exception):
    code = "LI-CAMPAIGN-002"


def next_batch(state: CampaignState, batches: list[Batch]) -> Batch | None:
    for b in batches:
        if b.index not in state.done_batches:
            return b
    return None


def budget_preflight(state: CampaignState, batch: Batch, cap_usd: float) -> None:
    if state.spent_usd + batch.est_cost_usd > cap_usd:
        raise BudgetRefusedError(
            f"batch {batch.index} (est ${batch.est_cost_usd:.4f}) would exceed cap ${cap_usd} "
            f"(spent ${state.spent_usd:.4f}); shrink the batch or raise the cap with disclosure"
        )


class BudgetRefusedError(Exception):
    code = "LI-CAMPAIGN-001"


def mark_done(state: CampaignState, batch: Batch, actual_cost: float, progress_path: Path, plan_fp: str, cap_usd: float) -> None:
    """Book actuals; if actuals blow the cap the campaign HALTS with disclosure."""
    state.done_batches.append(batch.index)
    state.spent_usd += actual_cost
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = progress_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "done_batches": state.done_batches,
                "spent_usd": state.spent_usd,
                "coverage_gaps": state.coverage_gaps,
                "plan_fingerprint": plan_fp,
            },
            indent=2,
            sort_keys=True,
        )
    )
    tmp.replace(progress_path)  # atomic-ish progress write
    if state.spent_usd > cap_usd:
        raise BudgetCapBreachedError(
            f"actual spend ${state.spent_usd:.4f} exceeded cap ${cap_usd} after batch {batch.index}; "
            "state recorded; campaign must stop or the cap must be amended with disclosure"
        )


class BudgetCapBreachedError(Exception):
    code = "LI-CAMPAIGN-003"
