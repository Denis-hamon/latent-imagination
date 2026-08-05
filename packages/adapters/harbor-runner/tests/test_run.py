"""harbor-runner: budget cap + sim-mode ATIF validity + remaining-tasks report."""

from __future__ import annotations

import json

from core_schema.trace import ExecutionTrace
from harbor_runner.run import AgentSpec, Budget, run_batch

TASKS = [
    {
        "instance_id": f"task-{i}",
        "repo_full_name": "django/django",
        "commit_sha": "c" * 40,
        "f2p_tests": [f"tests/t{i}.py::test_x"],
    }
    for i in range(10)
]

AGENT = AgentSpec(
    name="claude-code",
    version="2.1.0",
    model_name="claude-sonnet-4-6",
    model_family="claude",
    scaffold_version="0.20.0",
)


def test_sim_mode_emits_valid_atif(tmp_path):
    res = run_batch(TASKS[:3], AGENT, tmp_path, Budget(cap_usd=10.0), simulate=True)
    assert res.deposited == 3
    for f in res.trajectories_root.rglob("*.json"):
        ExecutionTrace.model_validate(json.loads(f.read_text()))


def test_budget_cap_stops_and_reports(tmp_path):
    # sim cost per task = 0.004; cap 0.01 → 2 tasks pass, 3rd fails, remainder reported
    res = run_batch(TASKS[:3], AGENT, tmp_path, Budget(cap_usd=0.01), simulate=True)
    assert res.stopped_by_budget
    assert res.deposited == 2
    report = json.loads(next(tmp_path.rglob("remaining-tasks.json")).read_text())
    assert report["remaining"] == ["task-2"]


def test_provenance_carried_in_extra(tmp_path):
    res = run_batch(TASKS[:1], AGENT, tmp_path, Budget(cap_usd=1.0), simulate=True)
    traj = json.loads(next(res.trajectories_root.rglob("sim-*.json")).read_text())
    assert traj["extra"]["provenance"]["scaffold_version"] == "0.20.0"
    assert traj["extra"]["attempt"]["env_fingerprint"]["container_image_digest"]
