"""Story 7.1 AC4: the revocation drill runs end-to-end OFFLINE — certificates
assembled under FR-21 doctrine, stored under prereg ownership, anchored on the
disclosed simulated lane, ledger rows appended in order (never edited), and the
gate seam hard-failing / authorizing exactly as the four drill states demand."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "prereg"))

import certificate_rehearsal as cr


@pytest.fixture()
def rehearsal(tmp_path):
    store = tmp_path / "store"
    report = tmp_path / "report.json"
    out = cr.main(["--store-root", str(store), "--report", str(report)])
    return store, report, out


def test_outcome_pass_and_anchor_disclosed_offline(rehearsal):
    _, report_path, out = rehearsal
    assert out["outcome"] == "PASS"
    report = json.loads(report_path.read_text())
    # disclosure, never silence: the anchor lane is explicit and simulated
    assert report["anchor_mode"] == [
        "ots-simulated (rehearsal, story 7.1 \u2014 no live anchor)"]
    assert report["doctrine"].startswith("REHEARSAL ONLY")


def test_ledger_is_append_only_in_order(rehearsal):
    store, _, _ = rehearsal
    rows = [json.loads(l) for l in (store / "prereg-ledger.jsonl").read_text().splitlines()]
    assert [r["type"] for r in rows] == ["certificate"] * 4
    assert [r["direction"] for r in rows] == ["issued", "superseding", "superseding", "superseding"]
    # each supersession names the previous certificate by hash (AD-3)
    assert rows[1]["supersedes"] == rows[0]["certificate_hash"]
    assert rows[2]["supersedes"] == rows[1]["certificate_hash"]
    assert rows[3]["supersedes"] == rows[2]["certificate_hash"]
    for r in rows:
        assert r["certified_precision"] <= 1.0 and r["registered_bar"] == pytest.approx(0.8889)


def test_store_zone_and_manifests_under_prereg_ownership(rehearsal):
    store, _, _ = rehearsal
    manifests = sorted((store / "prereg" / "manifests").glob("*.artifact.json"))
    assert {m.name.split(".")[0] for m in manifests} == {
        "rehearsal-cert-a", "rehearsal-cert-b", "rehearsal-cert-c", "rehearsal-cert-d"}
    for m in manifests:
        man = json.loads(m.read_text())
        assert man["artifact_type"] == "threshold-certificate"
        assert man["producer"] == "prereg"
        assert man["artifact_class"] == "reproducible"
        assert "created_at" not in man
    # simulate-proof artifacts landed next to the ledger discipline
    assert len(list((store / "proofs").glob("*.sim.ots"))) == 4


def test_drill_matrix_and_logged_refusals(rehearsal):
    store, report_path, _ = rehearsal
    report = json.loads(report_path.read_text())
    d = report["drill"]
    assert d["1-superseeded"]["result"] == "hard-fail"
    assert "superseded" in d["1-superseeded"]["reason"]
    assert d["2-below-bar"]["result"] == "hard-fail"
    assert "at/below" in d["2-below-bar"]["reason"]
    assert d["3-reprobe-crossed"]["result"] == "authorized"
    assert d["3-reprobe-crossed"]["certified_precision"] == pytest.approx(0.95)
    assert d["4-late-drift"]["result"] == "hard-fail"
    # AC3 "(logged)": every deny paired with a blocking_refused decision line
    decisions = store.parent / f"{store.name}-deployer" / "decisions.jsonl"
    lines = [json.loads(l) for l in decisions.read_text().splitlines()]
    assert report["refusals_logged"] == len(lines) == 3
    assert all(l["kind"] == "blocking_refused" for l in lines)


def test_non_empty_store_root_refused(tmp_path):
    """Append-only discipline: a rehearsal never reuses a populated root."""
    store = tmp_path / "store"
    store.mkdir()
    (store / "leftover").write_text("x")
    with pytest.raises(SystemExit, match="non-empty"):
        cr.main(["--store-root", str(store), "--report", str(tmp_path / "r.json")])
