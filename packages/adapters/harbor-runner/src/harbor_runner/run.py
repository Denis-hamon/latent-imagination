"""harbor-runner adapter — orchestrates pinned agents on pinned task envs.

Two modes:
- live: drives Harbor on the provisioned OVH instance (owner-run; evidence in
  governance/ovh/bootstrap.md)
- simulate: fabricates ATIF v1.7 trajectories with our `extra` payload — used
  by tests/CI and by campaign dry-runs. Must produce byte-valid ATIF.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from core_schema.identity import task_fingerprint

TRACE_SCHEMA = "ATIF-v1.7"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    version: str
    model_name: str
    model_family: str
    scaffold_version: str


@dataclass
class Budget:
    cap_usd: float
    spent_usd: float = 0.0

    def charge(self, usd: float) -> None:
        if self.spent_usd + usd > self.cap_usd:
            raise BudgetCapExceeded(f"cap {self.cap_usd} exceeded")
        self.spent_usd += usd


class BudgetCapExceeded(Exception):
    code = "LI-HARBOR-001"


@dataclass
class BatchResult:
    deposited: int
    stopped_by_budget: bool
    trajectories_root: Path


def _simulated_trace(task: dict[str, Any], agent: AgentSpec, seed: int) -> dict[str, Any]:
    task_id = task_fingerprint(task["repo_full_name"], task["commit_sha"], task["f2p_tests"])
    flip = seed % 3 == 0  # deterministic pseudo-behavior
    steps = [
        {
            "step_id": 1,
            "timestamp": "2026-08-05T10:00:00Z",
            "source": "user",
            "message": f"Fix the failing tests in {task['repo_full_name']}",
            "extra": {},
        },
        {
            "step_id": 2,
            "timestamp": "2026-08-05T10:00:12Z",
            "source": "agent",
            "model_name": agent.model_name,
            "llm_call_count": 1,
            "message": "Applying patch and running F2P tests.",
            "tool_calls": [
                {
                    "tool_call_id": "call_1",
                    "function_name": "bash",
                    "arguments": {"command": "git apply p.diff && pytest -q"},
                    "extra": {},
                }
            ],
            "observation": {
                "results": [
                    {
                        "source_call_id": "call_1",
                        "content": "1 passed in 0.42s" if flip else "FAILED 2 tests",
                        "extra": {},
                    }
                ]
            },
            "metrics": {"prompt_tokens": 500, "completion_tokens": 100, "cost_usd": 0.002},
            "extra": {},
        },
    ]
    return {
        "schema_version": TRACE_SCHEMA,
        "session_id": f"sim-{task_id[:8]}-{seed}",
        "agent": {
            "name": agent.name,
            "version": agent.version,
            "model_name": agent.model_name,
            "extra": {},
        },
        "steps": steps,
        "final_metrics": {
            "total_prompt_tokens": 500 * len(steps),
            "total_completion_tokens": 100 * len(steps),
            "total_cost_usd": 0.002 * len(steps),
            "total_steps": len(steps),
        },
        "extra": {
            "attempt": {
                "task_id": task_id,
                "env_fingerprint": {
                    "os_family": "linux",
                    "python_version": "3.12.8",
                    "deps_lock_sha256": "f" * 64,
                    "container_image_digest": f"sha256:sim{seed}",
                },
                "f2p_tests": list(task["f2p_tests"]),
                "scoring_seed": seed,
            },
            "provenance": {
                "model_family": agent.model_family,
                "model_version": agent.model_name,
                "scaffold_name": "harbor",
                "scaffold_version": agent.scaffold_version,
            },
            "cost_usd": 0.002 * len(steps),
        },
    }


def run_batch(
    tasks: list[dict[str, Any]],
    agent: AgentSpec,
    landing_root: Path,
    budget: Budget,
    *,
    simulate: bool = False,
    source_id: str = "own-harbor-seed",
) -> BatchResult:
    """Runs (or simulates) a batch. Budget cap = hard stop with remaining-batch report."""
    assert simulate, "live mode requires the provisioned OVH host; pass simulate=True in tests/dev"
    batch_id = f"{agent.name}-{sha256(agent.name.encode()).hexdigest()[:8]}"
    deposited = 0
    for i, task in enumerate(tasks):
        body = _simulated_trace(task, agent, seed=i)
        cost = body["final_metrics"]["total_cost_usd"]
        try:
            budget.charge(cost)
        except BudgetCapExceeded:
            _write_remaining_report(landing_root, source_id, batch_id, tasks[i:])
            return BatchResult(deposited=deposited, stopped_by_budget=True, trajectories_root=landing_root)
        dest = landing_root / source_id / batch_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"sim-{i:04d}.json").write_text(json.dumps(body, indent=2, sort_keys=True))
        deposited += 1
    return BatchResult(deposited=deposited, stopped_by_budget=False, trajectories_root=landing_root)


def _write_remaining_report(landing_root: Path, source_id: str, batch_id: str, remaining: list[dict[str, Any]]) -> None:
    dest = landing_root / source_id / batch_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "remaining-tasks.json").write_text(
        json.dumps({"remaining": [t.get("instance_id", t.get("repo_full_name")) for t in remaining]}, indent=2)
    )
