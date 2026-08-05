"""Proof tests for the AD-4 writer-inventory guard."""

from __future__ import annotations

from pathlib import Path

from tests.guards.writer_inventory import find_unauthorized_writers


def test_no_unauthorized_writers_on_real_tree():
    assert find_unauthorized_writers() == []


def test_guard_detects_unauthorized_writer(tmp_path):
    fake = tmp_path / "packages"
    ok = fake / "store" / "src" / "store"
    ok.mkdir(parents=True)
    (ok / "emit.py").write_text("x = write_table(t, p)\n")
    bad = fake / "probe" / "src" / "probe"
    bad.mkdir(parents=True)
    (bad / "sneaky.py").write_text("pq.write_table(t, p)\n")
    violations = find_unauthorized_writers(Path(fake))
    assert any("probe" in v for v in violations)
    assert not any("store" in v for v in violations)
