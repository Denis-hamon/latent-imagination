"""Slice assembly end-to-end on a synthetic landing items.json."""

from __future__ import annotations

import json
from pathlib import Path

from probe.slice_builder import assemble_slice


def test_slice_report_discloses_everything(tmp_path):
    items = [
        {"instance_id": "good-1", "FAIL_TO_PASS": ["pkg/tests/test_a.py::test_a"], "patch": "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-x\n+y\n"},
        {"instance_id": "bad-1", "FAIL_TO_PASS": ["pkg/tests/conftest.py::test_s"], "patch": "--- a/src/b.py\n+++ b/src/b.py\n@@ -1,1 +1,1 @@\n-x\n+y\n"},
        {"instance_id": "bad-2", "FAIL_TO_PASS": ["pkg/tests/test_c.py::test_c"], "patch": "--- a/pkg/tests/test_c.py\n+++ b/pkg/tests/test_c.py\n@@ -1,1 +1,1 @@\n-x\n+y\n"},
    ]
    items_path = tmp_path / "items.json"
    items_path.write_text(json.dumps(items))

    rep = assemble_slice(items_path, governance_root=tmp_path / "gov")
    assert rep.total_in == 3 and rep.kept == 1 and rep.rejected == 2
    assert abs(rep.reject_rate - 2 / 3) < 1e-12

    disc = (tmp_path / "gov" / "probe-design" / "clean-slice" / "DISCLOSURE.md").read_text()
    assert "kept: 1" in disc and "rejected: 2" in disc and "66.67%" in disc
    assert rep.out_path.exists()

    kept_items = json.loads(rep.out_path.read_text())
    assert [i["instance_id"] for i in kept_items] == ["good-1"]
