"""Labeling runner contract: pure rules, quarantine discipline, ledger rows."""

from __future__ import annotations

import pytest
from core_schema.domain import LabelOutcome
from labeling.rules_v1 import classify_tests_output
from labeling.runner import QuarantineCapExceeded, run_labeling
from store.validate import validate_store


def _attempts() -> list[dict]:
    return [
        {"attempt_id": "a" * 64, "task_id": "t", "raw_output": "1 passed in 0.2s", "start": "2026-08-05T10:00:00Z"},
        {"attempt_id": "b" * 64, "task_id": "t", "raw_output": "Segmentation fault (core dumped)", "start": "2026-08-05T10:01:00Z"},
        {"attempt_id": "c" * 64, "task_id": "t", "raw_output": "FAILED tests/x.py", "start": "2026-08-05T10:02:00Z"},
    ]


class TestRules:
    def test_classification_order(self):
        assert classify_tests_output("1 passed in 0.1s") == LabelOutcome.VALID_EXECUTION
        assert classify_tests_output("Segmentation fault") == LabelOutcome.FALSE_START_INFRASTRUCTURE_FAILURE
        assert classify_tests_output("connection timeout while resolving") is None  # quarantine
        assert classify_tests_output("FAILED 2 tests") == LabelOutcome.FALSE_START_TESTS_RAN_NO_FLIP

    def test_ambiguous_never_adjudicated(self):
        assert classify_tests_output("Killed by OOM watcher") is None


class TestRunner:
    def test_run_writes_validating_store_and_ledger(self, tmp_path):
        store = tmp_path / "store"
        res = run_labeling(
            _attempts(),
            store_root=store,
            run_id="run-001",
            store_snapshot="s" * 64,
            code_commit="c" * 40,
            now_utc="2026-08-05T12:00:00Z",
        )
        assert res.summary["labels"] == 3 and res.summary["quarantined"] == 0
        ledger = (store / "prereg-ledger.jsonl").read_text()
        assert '"type": "run"' in ledger and '"run_id": "run-001"' in ledger

        rep = validate_store(store)
        assert rep.checks.get("prereg-precedence") == "violation"  # no anchor row yet
        assert not rep.ok

    def test_quarantine_cap_halts(self, tmp_path):
        attempts = _attempts() + [
            {"attempt_id": "d" * 64, "task_id": "t", "raw_output": "request timed out", "start": "2026-08-05T10:03:00Z"},
        ]
        with pytest.raises(QuarantineCapExceeded):
            run_labeling(
                attempts,
                store_root=tmp_path / "store",
                run_id="run-x",
                store_snapshot="s" * 64,
                code_commit="c" * 40,
                quarantine_cap=0.10,
                now_utc="2026-08-05T12:00:00Z",
            )

    def test_replay_byte_identical(self, tmp_path):
        r1 = run_labeling(
            _attempts(),
            store_root=tmp_path / "s1",
            run_id="run-001",
            store_snapshot="s" * 64,
            code_commit="c" * 40,
            now_utc="2026-08-05T12:00:00Z",
        )
        r2 = run_labeling(
            _attempts(),
            store_root=tmp_path / "s2",
            run_id="run-001",
            store_snapshot="s" * 64,
            code_commit="c" * 40,
            now_utc="2026-08-05T12:00:00Z",
        )
        assert r1.summary["labels_sha256"] == r2.summary["labels_sha256"]
        assert r1.summary["quarantine_sha256"] == r2.summary["quarantine_sha256"]
