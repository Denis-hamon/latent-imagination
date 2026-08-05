"""Guard: prereg precedence end-to-end via store-validate + ledger (1.3↔1.4 wiring)."""

from __future__ import annotations

from pathlib import Path

from prereg.ledger import anchor_entry, append_entry, run_entry
from store.emit import write_artifact
from store.validate import validate_store


def _inputs(run_id: str) -> dict:
    return {
        "store_snapshot": "a" * 64,
        "ruleset_version": "rules-v1",
        "code_commit": "c" * 40,
        "seeds": {},
        "run_id": run_id,
    }


def _labels_store(tmp_path: Path) -> Path:
    root = tmp_path / "store"
    f = tmp_path / "labels.parquet"
    f.write_bytes(b"PAR1labels")
    write_artifact(
        "labeling", "labels", "labels-v0", "v0", [f], _inputs("run-1"), root
    )
    return root


def _ledger(root: Path, entries: list[dict]) -> Path:
    ledger = root / "prereg-ledger.jsonl"
    for e in entries:
        append_entry(ledger, e)
    return ledger


def test_precedence_ok_when_anchored_before(tmp_path):
    root = _labels_store(tmp_path)
    _ledger(root, [
        anchor_entry("x" * 64, "e" * 64, "2026-08-04T10:00:00Z", "p.ots"),
        run_entry("run-1", "2026-08-05T10:00:00Z", "e" * 64, "s" * 64),
    ])
    report = validate_store(root)
    assert report.checks.get("prereg-precedence") == "ok", report.errors


# validate_store report has .errors list not method; adjust assertion helper


def test_precedence_violation_when_anchored_after(tmp_path):
    root = _labels_store(tmp_path)
    _ledger(root, [
        anchor_entry("x" * 64, "e" * 64, "2026-08-06T10:00:00Z", "p.ots"),
        run_entry("run-1", "2026-08-05T10:00:00Z", "e" * 64, "s" * 64),
    ])
    report = validate_store(root)
    assert report.checks.get("prereg-precedence") == "violation"
    assert not report.ok
