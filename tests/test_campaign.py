"""Campaign driver tests: batching, resume, cap refusal, coverage bookkeeping."""

from __future__ import annotations

import pytest

from scripts.act1.campaign import (
    BudgetRefusedError,
    CampaignState,
    budget_preflight,
    mark_done,
    next_batch,
    plan_batches,
    plan_fingerprint,
    resume_state,
)

TASKS = [{"instance_id": f"t{i}"} for i in range(10)]
FP = plan_fingerprint(TASKS, 3)


def _batches():
    return plan_batches(TASKS, batch_size=3, cost_per_task_usd=0.01)
    # 4 batches: 3,3,3,1


def test_plan_shape():
    b = _batches()
    assert len(b) == 4
    assert b[-1].est_cost_usd == pytest.approx(0.01)


def test_resume_skips_done(tmp_path):
    state = CampaignState([0, 1], 0.06, [])
    nxt = next_batch(state, _batches())
    assert nxt.index == 2


def test_resume_refuses_plan_drift(tmp_path):
    p = tmp_path / "progress.json"
    state = CampaignState([], 0.0, [])
    mark_done(state, _batches()[0], 0.031, p, FP, cap_usd=10.0)
    shifted = [{"instance_id": "NEW"}] + TASKS[:-1]
    with pytest.raises(Exception, match="plan"):
        resume_state(p, plan_fingerprint(shifted, 3))


def test_budget_preflight_refuses(tmp_path):
    state = CampaignState([], 0.09, [])
    with pytest.raises(BudgetRefusedError, match="exceed cap"):
        budget_preflight(state, _batches()[2], cap_usd=0.10)


def test_mark_done_persists_progress(tmp_path):
    p = tmp_path / "progress.json"
    state = CampaignState([], 0.0, [])
    mark_done(state, _batches()[0], 0.031, p, FP, cap_usd=10.0)
    back = resume_state(p, FP)
    assert back.done_batches == [0]
    assert back.spent_usd == pytest.approx(0.031)
