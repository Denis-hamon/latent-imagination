"""mcp_flywheel stages (collect → assemble → promote-report) — hermetic: the
label gate rejects ungrounded self-declarations, dedup against pool + batch,
goal-free provenance preserved, promote-report never fakes geometry (discloses
embed-pending when the node NPZ is absent)."""

from __future__ import annotations

import importlib.util
import json
from hashlib import sha256
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "mcp_flywheel", Path(__file__).resolve().parent / "mcp_flywheel.py")
fw = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fw)


def _scan(call_id: str, *, diff: str, state: str = "state text", decision="abstain",
          reporter="", conf=0.01) -> dict:
    return {"ts": "2026-08-15T14:00:00Z", "call_id": call_id, "type": "risk_scan",
            "decision": decision, "attractor_score": -0.03, "confidence": conf,
            "exclude_task": "", "reporter": reporter, "reporter_missing": not reporter,
            "state_sha": sha256(state.encode()).hexdigest(),
            "diff_sha": sha256(diff.encode()).hexdigest(),
            "state_text": state, "diff_text": diff}


def _outcome(call_id: str, passed: bool, *, reporter="", grounded_by="") -> dict:
    return {"ts": "2026-08-15T14:05:00Z", "call_id": call_id, "type": "outcome",
            "passed": passed, "reporter": reporter, "grounded_by": grounded_by}


@pytest.fixture()
def world(tmp_path, monkeypatch):
    log = tmp_path / "mcp-log.jsonl"
    out = tmp_path / "flywheel"
    pool = tmp_path / "pool.json"
    pool.write_text(json.dumps(
        [{"task": "t-pool", "arm": "off", "campaign": "x", "state": "s",
          "goal": "g", "diff": "already-in-pool-diff", "y": 0}]))
    monkeypatch.setattr(fw, "LOG", log)
    monkeypatch.setattr(fw, "OUT", out)
    monkeypatch.setattr(fw, "RUNS_LOG", out / "runs.log")
    monkeypatch.setattr(fw, "HISTORY", out / "history")
    monkeypatch.setattr(fw, "POOL_JSON", pool)
    monkeypatch.setattr(fw, "STAGE2_ROWS", out / "flywheel-rows.json")
    monkeypatch.setattr(fw, "STAGE2_REPORT", out / "promote-report.json")
    monkeypatch.setattr(fw, "V9_JSON", tmp_path / "latent-pool-v9.json")
    monkeypatch.setattr(fw, "V9_NPZ", tmp_path / "latent-pool-v9.npz")
    monkeypatch.setattr(fw, "V9_CALIB", tmp_path / "risk-scan-v9-calibration.json")
    return {"tmp": tmp_path, "log": log, "out": out, "pool": pool}


def _write_log(log: Path, entries: list[dict]) -> None:
    lines = [json.dumps(e) for e in entries]
    lines.insert(2, "{torn")
    log.write_text("\n".join(lines) + "\n")


class TestCollect:
    def test_pairing_ground_and_stratify(self, world):
        _write_log(world["log"], [
            _scan("c1", diff="diff-one", reporter="model-a"),
            _scan("c2", diff="diff-two", reporter="model-b"),
            _scan("c3", diff="diff-three", reporter=""),           # no outcome -> unmatched
            _outcome("c1", True, reporter="model-a", grounded_by="pytest-f2p"),
            _outcome("c2", False, reporter="model-b", grounded_by=""),  # NOT grounded
            _outcome("zz", True, reporter="x", grounded_by="pytest"),   # unmatched
        ])
        assert fw.main() == 0
        report = json.loads((world["out"] / "collect-report.json").read_text())
        assert report["risk_scan_avec_capture"] == 3
        assert report["outcomes"] == 3
        assert report["outcomes_non_appariés"] == 1
        assert report["outcomes_non_groundés_rejetés"] == 1
        assert report["paires_promouvables"] == 1
        cands = json.loads((world["out"] / "candidates.json").read_text())
        assert len(cands) == 1 and cands[0]["call_id"] == "c1"
        assert cands[0]["grounded_by"] == "pytest-f2p"
        assert report["par_auteur"]["model-a"]["n"] == 1
        assert report["par_auteur"]["model-b"]["n"] == 1  # counted, pair rejected

    def test_absent_log_is_honest_zero(self, world):
        assert fw.main() == 0  # prints "aucun trafic MCP encore", exits 0


class TestAssemble:
    @staticmethod
    def _candidate(call_id, diff, passed=True, grounded_by="pytest-f2p", reporter="model-a"):
        return {"call_id": call_id, "reporter": reporter, "grounded_by": grounded_by,
                "passed": passed, "state_text": "state", "diff_text": diff,
                "state_sha": None, "diff_sha": None,
                "server_decision": "abstain", "server_confidence": 0.01,
                "exclude_task": "", "collected_at": "2026-08-15T14:05:00Z"}

    def _write_candidates(self, world, cands):
        world["out"].mkdir(parents=True, exist_ok=True)
        (world["out"] / "candidates.json").write_text(json.dumps(cands))

    def test_label_gate_and_provenance(self, world):
        self._write_candidates(world, [self._candidate("c1", "new-diff-A")])
        assert fw.assemble() == 0
        rows = json.loads(fw.STAGE2_ROWS.read_text())
        assert len(rows) == 1
        r = rows[0]
        assert r["y"] == 1
        assert r["goal_free"] is True
        assert r["campaign"] == "mcp-flywheel-1"
        assert r["task"].startswith("flywheel:")
        prov = r["provenance"]
        assert prov["call_id"] == "c1" and prov["reporter"] == "model-a"
        assert prov["diff_sha256"] == sha256(b"new-diff-A").hexdigest()

    def test_failed_outcome_labels_negative(self, world):
        self._write_candidates(world, [self._candidate("c1", "a-diff", passed=False)])
        fw.assemble()
        rows = json.loads(fw.STAGE2_ROWS.read_text())
        assert rows[0]["y"] == 0

    def test_ungrounded_rejected(self, world):
        self._write_candidates(world, [
            self._candidate("c1", "a-diff"),
            self._candidate("c2", "b-diff", grounded_by=""),  # self-declared, no method
        ])
        fw.assemble()
        summary = json.loads((world["out"] / "assemble-report.json").read_text())
        assert summary["rows_out"] == 1
        assert summary["rejected"]["not_grounded"] == 1

    def test_dedup_against_pool_and_batch(self, world):
        # pool fixture contains "already-in-pool-diff"; assemble must drop it +
        # drop an in-batch duplicate, keeping the two distinct fresh diffs.
        self._write_candidates(world, [
            self._candidate("c1", "already-in-pool-diff"),
            self._candidate("c2", "dup-diff"),
            self._candidate("c3", "dup-diff", passed=False, grounded_by="ci"),
            self._candidate("c4", "fresh-diff", passed=False, grounded_by="human"),
        ])
        assert fw.assemble() == 0
        summary = json.loads((world["out"] / "assemble-report.json").read_text())
        assert summary["rejected"] == {"not_grounded": 0, "dup_pool": 1, "dup_batch": 1}
        assert summary["rows_out"] == 2
        assert summary["positives"] == 1  # c2 passed, c4 failed
        assert summary["all_goal_free"] is True

    def test_assemble_without_candidates_halts_cleanly(self, world, capsys):
        assert fw.assemble() == 0
        assert "candidates.json absent" in capsys.readouterr().out


class TestCadenceJournalAndHistory:
    """Story 9.2: attempt journal (R4), missing-reporter surfacing, dated
    history snapshots — a crashed run must read as interrupted, never silent."""

    def test_collect_journals_the_attempt_and_counts_missing_reporters(self, world):
        _write_log(world["log"], [
            _scan("c1", diff="diff-A", reporter="model-a"),
            _scan("c2", diff="diff-B", reporter=""),          # missing reporter
            _outcome("c1", True, reporter="model-a", grounded_by="pytest-f2p"),
            _outcome("c2", True, reporter="", grounded_by="pytest-f2p"),
        ])
        rc = fw._dispatch([str(world["log"]), "--stage", "collect"])
        assert rc == 0
        lines = [json.loads(l) for l in (world["out"] / "runs.log").read_text().splitlines()]
        assert len(lines) == 1 and lines[0]["stage"] == "collect" and lines[0]["exit"] == 0
        assert lines[0]["paires_promouvables"] == 2
        rep = json.loads((world["out"] / "collect-report.json").read_text())
        assert rep["scans_sans_reporter"] == 1  # surfaced, never silent

    def test_history_snapshot_is_dated_and_append_safe(self, world):
        _write_log(world["log"], [
            _scan("c1", diff="diff-A", reporter="m"),
            _outcome("c1", True, reporter="m", grounded_by="pytest-f2p"),
        ])
        assert fw._dispatch([str(world["log"]), "--stage", "collect"]) == 0
        snaps = list((world["out"] / "history").glob("collect-report-*.json"))
        assert len(snaps) == 1  # first run -> one dated copy
        from scripts.act2.mcp_flywheel import _history_snapshot
        _history_snapshot("collect-report.json")  # same second -> no dup
        assert len(list((world["out"] / "history").glob("collect-report-*.json"))) == 1

    def test_assemble_journals_too(self, world):
        _write_log(world["log"], [
            _scan("c1", diff="diff-A", reporter="m"),
            _outcome("c1", True, reporter="m", grounded_by="pytest-f2p"),
        ])
        assert fw._dispatch([str(world["log"]), "--stage", "collect"]) == 0
        assert fw._dispatch(["--stage", "assemble"]) == 0
        lines = [json.loads(l) for l in (world["out"] / "runs.log").read_text().splitlines()]
        assert [l["stage"] for l in lines] == ["collect", "assemble"]
        assert lines[1]["rows_out"] == 1
        assert list((world["out"] / "history").glob("assemble-report-*.json"))


class TestPromoteReport:
    def test_never_fakes_geometry(self, world):
        _write_log(world["log"], [
            _scan("c1", diff="some-diff", reporter="m"),
            _outcome("c1", True, grounded_by="pytest-f2p"),
        ])
        fw.main()
        fw.assemble()
        assert fw.promote_report() == 0
        rep = json.loads(fw.STAGE2_REPORT.read_text())
        assert rep["v9_npz_present"] is False
        assert "EMBED PENDING ON NODE" in rep["status"]
        assert rep["v8"]["sha256_pool_json"] == sha256(world["pool"].read_bytes()).hexdigest()
        assert rep["flywheel_rows"] == 1
        assert "goal_free" in rep["goal_free_note"]
        assert rep["rollback"]

    def test_promote_without_assemble_halts_cleanly(self, world, capsys):
        assert fw.promote_report() == 0
        assert "absent" in capsys.readouterr().out
