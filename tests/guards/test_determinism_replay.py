"""Guard: labeling replay determinism (AD-7) — over the REAL runner now."""

from __future__ import annotations

from labeling.runner import assert_replay_identical

ATTEMPTS = [
    {"attempt_id": "a" * 64, "task_id": "t1", "raw_output": "1 passed in 0.1s", "start": "2026-08-05T10:00:00Z", "source_class": "own_harbor_run"},
    {"attempt_id": "b" * 64, "task_id": "t1", "raw_output": "Segmentation fault", "start": "2026-08-05T10:01:00Z", "source_class": "own_harbor_run"},
]


def _run(tmp_path, name):
    return assert_replay_identical(
        ATTEMPTS,
        root_a=tmp_path / f"{name}-a",
        root_b=tmp_path / f"{name}-b",
        run_id="replay-check",
        store_snapshot="s" * 64,
        code_commit="c" * 40,
        now_utc="2026-08-05T12:00:00Z",
    )


def test_real_runner_replay_is_byte_identical(tmp_path):
    _run(tmp_path, "x")


def test_real_runner_detects_nondeterminism(tmp_path, monkeypatch):
    import json as _json

    from labeling import runner as runner_mod

    orig = runner_mod._labels_bytes
    calls = {"n": 0}

    def flaky(labels):
        out = _json.loads(orig(labels))
        calls["n"] += 1
        out.append({"meta_run_marker": calls["n"]})  # run A: 1, run B: 2
        return orig(out)

    monkeypatch.setattr(runner_mod, "_labels_bytes", flaky)
    try:
        _run(tmp_path, "y")
    except AssertionError as e:
        assert "byte-identical" in str(e)
    else:  # pragma: no cover
        raise AssertionError("injected nondeterminism went unnoticed")
