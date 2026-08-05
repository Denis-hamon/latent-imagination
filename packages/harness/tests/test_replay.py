"""Replay export + check: function-proving fixtures (AC1, AC2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from harness.replay_check import replay_check
from harness.replay_export import export_bundle

PIPELINE = '''
import sys, json
from pathlib import Path
import argparse

p = argparse.ArgumentParser()
p.add_argument("--slice", required=True)
p.add_argument("--out", required=True)
a = p.parse_args()

total = 0
flipped = 0
for f in sorted(Path(a.slice).glob("*.json")):
    rows = json.loads(f.read_text())
    total += len(rows)
    flipped += sum(1 for r in rows if r.get("flipped"))
Path(a.out, "figure.json").write_text(json.dumps({"n": total, "flipped": flipped}))
'''


@pytest.fixture()
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "src-slice").mkdir()
    (tmp_path / "src-slice" / "slice-0.json").write_text(
        json.dumps([{"id": "a1", "flipped": True}, {"id": "a2", "flipped": False}])
    )
    (tmp_path / "src-rules").mkdir()
    (tmp_path / "src-rules" / "rules-v1.toml").write_text('version = "rules-v1"\n')
    (tmp_path / "src-pipeline").mkdir()
    (tmp_path / "src-pipeline" / "run.py").write_text(PIPELINE)
    b = export_bundle(
        tmp_path / "bundle",
        slice_files=[tmp_path / "src-slice" / "slice-0.json"],
        rules_files=[tmp_path / "src-rules" / "rules-v1.toml"],
        pipeline_files=[tmp_path / "src-pipeline" / "run.py"],
        inputs={"store_snapshot": "s" * 64, "ruleset_version": "rules-v1", "code_commit": "c" * 40, "seeds": {}},
    )
    return b.path


def test_bundle_is_self_contained_and_content_only(bundle: Path):
    man = json.loads((bundle / "manifest.json").read_text())
    assert "created_at" not in man  # reproducible class (AD-7)
    assert man["inputs"]["ruleset_version"] == "rules-v1"
    assert man["bundle_hash"]
    assert (bundle / "pipeline" / "run.py").read_text() == PIPELINE  # code embedded


def test_replay_check_ok_with_own_computation(bundle: Path):
    # companion computes expected figure bytes the way the pipeline does
    work = bundle / "out-expected"
    work.mkdir()
    import subprocess
    import sys

    env = {"PYTHONPATH": ""}
    subprocess.run(
        [sys.executable, str(bundle / "pipeline" / "run.py"), "--slice", str(bundle / "slice"), "--out", str(work)],
        check=True, env=env,
    )
    expected_bytes = (work / "figure.json").read_bytes()
    from hashlib import sha256 as _sha

    (bundle / "expected.json").write_text(json.dumps({"figure.json": _sha(expected_bytes).hexdigest()}))
    report = replay_check(bundle, bundle / "expected.json")
    assert report.ok, report.mismatches


def test_replay_check_flags_any_drift(bundle: Path):
    (bundle / "expected.json").write_text(json.dumps({"figure.json": "0" * 64}))
    report = replay_check(bundle, bundle / "expected.json")
    assert not report.ok
    assert "figure.json" in report.mismatches[0] if isinstance(report.mismatches[0], str) else True
