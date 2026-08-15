"""Story 10.1 budget-harness tests — stop-at-cap, shared Q1+Q2 budget,
per-quota no-diff abort, honest panel (no faked extraction).

Hermetic: the author model is monkeypatched out (no network — AD-6); the cap
and abort counters are real. These prove the envelope discipline, not the
model.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "genfam_gen", Path(__file__).resolve().parent / "genfam_gen.py")
gg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gg)


def _task(iid: str = "acme__repo.deadbeef.func_x__slot1", diff_ok: bool = True):
    return {
        "instance_id": iid, "family": "acme__repo", "campaign": "genfam-q1",
        "window": "gen-families-v1", "image": "x", "patch": "p", "target": "f.py",
        "f2p": ["tests/test_a.py::test_b"],
        "problem": "Fix the thing.", "_buggy": "def f():\n    return 1\n",
        "_diff_ok": diff_ok,
    }


def _fake_gen_patch(reply_diff: str):
    def _gp(task, feedback=""):
        return {"prompt_sha256": "p" * 64, "reply_sha256": "r" * 64,
                "raw_reply": reply_diff if task.get("_diff_ok", True) else "no diff here",
                "usage": {}, "api_calls": 1}
    return _gp


def test_call_budget_boundary():
    gg.call_budget(349, 350)  # under cap: fine
    with pytest.raises(gg.BudgetExhausted):
        gg.call_budget(350, 350)  # AT cap: refuse the 351st BEFORE it starts


def test_nodiff_abort_rate_needs_minimum_sample():
    assert gg.nodiff_abort_rate(4, 4) is None  # <5 slots: not enough to judge
    assert gg.nodiff_abort_rate(5, 4) == pytest.approx(0.8)  # 80% > 60%


def test_window_calls_counts_both_quotas(tmp_path, monkeypatch):
    monkeypatch.setattr(gg, "JOBS", tmp_path)
    for q in ("q1", "q2"):
        log = tmp_path / f"genfam-{q}" / "call-log.jsonl"
        log.parent.mkdir(parents=True)
        log.write_text("".join(json.dumps({"slot": f"s{q}{i}"}) + "\n" for i in range(3)))
    assert gg.window_calls_used() == 6  # cap is Q1+Q2 TOGETHER
    # restart-safe: cap is read from persisted log, not an in-process counter


def test_stop_at_cap_halts_cleanly_and_discloses(tmp_path, monkeypatch):
    monkeypatch.setattr(gg, "JOBS", tmp_path)
    results = tmp_path / "gen-results"; log = tmp_path / "call-log.jsonl"
    good_diff = "--- a/f.py\n+++ b/f.py\n@@\n-def f():\n-    return 1\n+def f():\n+    return 2\n"
    # make full-file regen path produce a diff
    monkeypatch.setattr(gg.pr, "gen_patch", _fake_gen_patch("```python\ndef f():\n    return 2\n```"))
    monkeypatch.setattr(gg.pr, "extract_full_file", lambda t: t.strip("`python\n ") or None)
    monkeypatch.setattr(gg.pr, "make_diff", lambda o, m, rel: good_diff)
    panel = [_task(f"acme__repo.deadbeef.func_{i}__s", True) for i in range(3)]
    with pytest.raises(SystemExit, match="STOP au plafond"):
        gg.gen_panel("q1", panel, draws=2, cap=3, results=results, log=log)
    summary = json.loads((results / "summary.json").read_text())
    assert summary["aborted"] == "cap-reached" and summary["calls_used"] == 3
    assert log.read_text().count("\n") == 3  # exactly 3 calls logged, 351st never started
    # slots interrompus par le budget: rec.json = budget-stopped, JAMAIS comptés no-diff
    recs = [json.loads(f.read_text()) for f in results.glob("*/rec.json")]
    stopped = [r for r in recs if r["status"] == "budget-stopped"]
    assert len(stopped) == 3 and all(r["status"] == "ok" for r in recs if r not in stopped)


def test_nodiff_abort_halts_with_disclosure(tmp_path, monkeypatch):
    monkeypatch.setattr(gg, "JOBS", tmp_path)
    results = tmp_path / "gen-results"; log = tmp_path / "call-log.jsonl"
    monkeypatch.setattr(gg.pr, "gen_patch", _fake_gen_patch("I cannot produce a diff"))
    monkeypatch.setattr(gg.pr, "extract_full_file", lambda t: None)
    monkeypatch.setattr(gg.pr, "extract_diff_sanitized", lambda t: None)
    panel = [_task(f"acme__repo.deadbeef.func_{i}__s", False) for i in range(6)]
    with pytest.raises(SystemExit, match=r"HALT q1: no-diff rate"):
        gg.gen_panel("q1", panel, draws=1, cap=50, results=results, log=log)
    summary = json.loads((results / "summary.json").read_text())
    assert summary["aborted"].startswith("no-diff>60%")


def test_load_panel_never_fakes_missing_extraction(tmp_path, monkeypatch):
    monkeypatch.setattr(gg, "JOBS", tmp_path)
    (tmp_path / "genfam-q1").mkdir(parents=True)
    (tmp_path / "genfam-q1" / "staging-extract.json").write_text(json.dumps(
        {"tasks": [{"instance_id": "a__b.c.func_x__s1", "problem": "p", "f2p": ["t"],
                    "target": "f.py", "campaign": "genfam-q1"}]}))
    sel = {"q1": [{"instance_id": "a__b.c.func_x__s1"}]}
    # no .buggy.py on disk -> the slot is NOT faked into the panel
    assert gg.load_panel("q1", sel) == []
    (tmp_path / "genfam-q1" / "a__b.c.func_x__s1.buggy.py").write_text("x = 1\n")
    panel = gg.load_panel("q1", sel)
    assert len(panel) == 1 and panel[0]["_buggy"] == "x = 1\n"
