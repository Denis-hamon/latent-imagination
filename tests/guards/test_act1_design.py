"""Story 2.1: claim-point design package + precedence on a REAL labeling run."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

GOV = Path(__file__).resolve().parents[2] / "governance" / "act1-design"


class TestDesignPackage:
    def test_required_files_exist(self):
        for f in ("tasks.toml", "design.toml", "RATIONALE.md", "coverage.md", "hash.py"):
            assert (GOV / f).exists(), f

    def test_design_toml_shape(self):
        d = tomllib.loads((GOV / "design.toml").read_text())
        assert d["attempt_protocol"]["stop_rule"] == "stop-at-first-valid"
        assert len(d["families"]["list"]) >= 3
        assert d["aggregation"]["primary"] == "macro_per_task"
        assert d["quarantine_flaky"]["quarantine_cap"] == 0.10
        assert d["tolerances"]["inclusivity"] == "inclusive"

    def test_tasks_pins_suites(self):
        d = tomllib.loads((GOV / "tasks.toml").read_text())
        suites = {t["suite"] for t in d["task"]}
        assert suites == {"django", "scikit-learn", "sympy"}

    def test_hash_deterministic_and_content_addressed(self):
        import sys

        sys.path.insert(0, str(GOV))
        from hash import design_package_hash

        assert design_package_hash(GOV) == design_package_hash(GOV)


class TestAnchoredPrecedenceOnRealRunner:
    """Fixture-anchored proving — lives BEFORE any field run, via the real path."""

    def test_fixture_anchor_before_run_yields_ok(self, tmp_path):
        from labeling.runner import run_labeling
        from prereg.ledger import anchor_entry, append_entry

        store = tmp_path / "store"
        res = run_labeling(
            [
                {"attempt_id": "a" * 64, "task_id": "t1", "raw_output": "1 passed", "start": "2026-08-05T10:00:00Z", "source_class": "own_harbor_run"},
            ],
            store_root=store,
            run_id="run-001",
            store_snapshot="s" * 64,
            code_commit="c" * 40,
            now_utc="2026-08-05T12:00:00Z",
        )
        append_entry(
            store / "prereg-ledger.jsonl",
            anchor_entry("x" * 64, res.summary["ruleset_hash"], "2026-08-04T10:00:00Z", "p.ots"),
        )
        from store.validate import validate_store

        rep = validate_store(store)
        assert rep.ok, rep.errors
        assert rep.checks.get("prereg-precedence") == "ok"
