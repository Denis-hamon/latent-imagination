"""Bit-rot tripwire for the public demo (story 5.5, FR-25/§9): when the landing
parquet is available, the demo re-runs clean and its record is well-formed,
sanitized, and dataset-linked. Skips (green) when the parquet is absent (CI)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pytest import TempPathFactory

REPO = Path(__file__).resolve().parents[2]
PARQUET = REPO / "data" / "landing" / "swe-bench-verified" / "v1" / "raw" / "0.parquet"


@pytest.mark.skipif(not PARQUET.exists(), reason="landing parquet absent (CI/scratch)")
def test_demo_reruns_and_the_record_is_sane(tmp_path_factory: TempPathFactory):
    demo = REPO / "demo" / "gate-advisory"
    record = demo / "record"
    scratch = tmp_path_factory.mktemp("demo-record")  # NEVER into the committed record
    before = (record / "demo-record.json").read_text() if (record / "demo-record.json").exists() else None
    r = subprocess.run([sys.executable, str(demo / "run_demo.py"), "--items", "3",
                        "--record-dir", str(scratch)],
                       capture_output=True, text=True, cwd=REPO, check=False)
    assert r.returncode == 0, r.stderr
    assert (record / "demo-record.json").read_text() == (before or (record / "demo-record.json").read_text())
    cap = json.loads((scratch / "demo-record.json").read_text())
    assert cap["input_parquet_sha256"]
    assert cap["sanitize_counts"] == {}  # proven clean, not presumed
    assert len(cap["items"]) == 3
    for line in (scratch / "decisions.jsonl").read_text().splitlines():
        ev = json.loads(line)
        assert ev["payload"]["candidate"]["wire_payload_sha256"]
        assert "note" in ev["payload"]["predictor_disclosure"]  # fixture marker survives
    assert before is None or json.loads(before)["items"][0]["instance_id"] == cap["items"][0]["instance_id"]


def test_consistency_driver_reruns(tmp_path):
    """Story 8.3: the evaluation driver runs end-to-end from a fresh clone
    (fixture records, committed split manifest) and publishes a store artifact."""
    import subprocess
    import sys

    drv = REPO / "scripts" / "ranking" / "run_consistency.py"
    store = tmp_path / "store"
    r = subprocess.run([sys.executable, str(drv), "--records",
                        str(REPO / "governance" / "ranking" / "consistency-fixture.json"),
                        "--store", str(store)],
                       capture_output=True, text=True, cwd=REPO, check=False)
    assert r.returncode == 0, r.stderr
    assert (store / "canonical" / "ordering-consistency" / "v0" / "consistency-report.json").is_file()
