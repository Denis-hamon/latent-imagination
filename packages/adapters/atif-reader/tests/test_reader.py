"""atif-reader tests: golden deposit + rejection counts (function-proven)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from atif_reader.reader import deposit_trajectories

GOLDEN = (
    Path(__file__).resolve().parents[3]
    / "core-schema"
    / "tests"
    / "fixtures"
    / "valid_trace_v1.json"
)


def _src(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    shutil.copy(GOLDEN, src / "good.json")
    bad = json.loads(GOLDEN.read_text())
    del bad["agent"]["name"]  # breaks required field
    (src / "bad.json").write_text(json.dumps(bad))
    return src


def test_deposit_counts_and_manifest(tmp_path):
    src = _src(tmp_path)
    landing = tmp_path / "landing"
    res = deposit_trajectories(src, landing, "public-traject-seed", "batch-001")
    assert res.deposited == 1 and res.rejected == 1
    manifest = json.loads(res.manifest_path.read_text())
    assert manifest["deposited"][0]["sha256"]
    assert manifest["rejected"][0]["name"] == "bad.json"
    # occurrence metadata present: produced_at allowed in landing manifests
    assert manifest["origin"] == "atif-reader"
