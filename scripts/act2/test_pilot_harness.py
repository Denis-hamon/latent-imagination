"""Pilot harness (Act II window) — wired with MockTransport, zero model call."""

from __future__ import annotations

from scripts.act2.pilot_harness import advisory_score, extract_diff, pilot_tasks


def test_pilot_tasks_are_bounded_and_real():
    tasks = pilot_tasks()
    assert len(tasks) == 4  # registered reality: the executed window covers 4
    assert all(t.image.startswith("jyangballin/swesmith") for t in tasks)
    assert all(len(t.f2p) > 0 for t in tasks)


def test_extract_diff_handles_fenced_and_bare():
    assert extract_diff("```diff\ndiff --git a/x b/x\n+1\n```") == "diff --git a/x b/x\n+1\n"
    assert extract_diff("some prose\ndiff --git a/y b/y\n+2\n") == "diff --git a/y b/y\n+2\n"
    assert extract_diff("no patch here") is None


def test_advisory_score_returns_finite_probability():
    # existing fixture-backed artifact always returns a valid probability
    p = advisory_score("diff --git a/x b/x\n+fix\n")
    assert 0.0 <= p <= 1.0
    p2 = advisory_score("")
    assert 0.0 <= p2 <= 1.0
