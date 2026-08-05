"""Replay bundle assembly tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from harness.replay_bundle import assemble_replay_bundle


def _srcs(tmp_path: Path):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "slice.json").write_text(json.dumps([{"id": "a1", "flipped": True}]))
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "rules.toml").write_text('v="rules-v1"\n')
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "run.py").write_text("print('ok')\n")
    return (
        tmp_path / "s" / "slice.json",
        tmp_path / "r" / "rules.toml",
        tmp_path / "p" / "run.py",
    )


def test_bundle_records_ladder_and_inputs(tmp_path):
    s, r, p = _srcs(tmp_path)
    path = assemble_replay_bundle(
        tmp_path / "bundles",
        slice_files=[s],
        rules_files=[r],
        pipeline_files=[p],
        inputs={"store_snapshot": "s" * 64, "ruleset_version": "rules-v1", "code_commit": "c" * 40, "seeds": {}},
        figure_id="erbve_curve_v1",
        ladder="small",
    )
    man = json.loads((path / "manifest.json").read_text())
    assert man["inputs"]["ladder"] == "small"
    assert man["inputs"]["figure_id"] == "erbve_curve_v1"


def test_unknown_ladder_rejected(tmp_path):
    s, r, p = _srcs(tmp_path)
    with pytest.raises(ValueError):
        assemble_replay_bundle(
            tmp_path / "bundles",
            slice_files=[s],
            rules_files=[r],
            pipeline_files=[p],
            inputs={},
            figure_id="f",
            ladder="huge",
        )
