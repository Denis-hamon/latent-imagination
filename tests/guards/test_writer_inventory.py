"""Proof tests for the AD-4 writer-inventory guard."""

from __future__ import annotations

from pathlib import Path

from tests.guards.writer_inventory import find_unauthorized_writers


def test_no_unauthorized_writers_on_real_tree():
    assert find_unauthorized_writers() == []


def test_guard_detects_unauthorized_writer(tmp_path):
    fake = tmp_path / "packages"
    ok = fake / "probe" / "src" / "probe"
    ok.mkdir(parents=True)
    # legitimate: writes its own design manifests (no store path)
    (ok / "manifests.py").write_text('p.write_text("out", encoding="utf-8")  # governance/ only\n')
    bad = fake / "probe2" / "src" / "probe2"
    bad.mkdir(parents=True)
    # violation: non-owning package writes into the canonical store
    (bad / "sneaky.py").write_text(
        'pq.write_table(t, store_root / "canonical" / "x")\n'
        'Path(store_root / "labels" / "y").write_text("z")\n'
    )
    ad = fake / "adapters" / "edge"
    (ad / "src" / "edge").mkdir(parents=True)
    (ad / "src" / "edge" / "dep.py").write_text("write_bytes(b)\n")  # adapters exempt (landing)
    violations = find_unauthorized_writers(Path(fake))
    assert not any(v.startswith("probe:") for v in violations)
    assert any(v.startswith("probe2:") for v in violations)
    assert not any(v.startswith("edge") for v in violations)


def test_guard_scans_scripts_scope(tmp_path):
    """Story 4.1 / deferred-work Epic-1: scripts are no longer a guard blind spot."""
    fake_pkg = tmp_path / "packages"
    fake_pkg.mkdir()
    scripts = tmp_path / "scripts"
    # sanctioned ceremony surface: store-aimed writes allowed by design
    (scripts / "prereg").mkdir(parents=True)
    (scripts / "prereg" / "ceremony.py").write_text(
        'Path(store_root / "prereg" / "x").write_text("ledger")\n'
    )
    # unsanctioned script writing to a store path → violation
    (scripts / "corpus").mkdir(parents=True)
    (scripts / "corpus" / "harvest.py").write_text(
        'pq.write_table(t, store_root / "canonical" / "corpus")\n'
    )
    violations = find_unauthorized_writers(Path(fake_pkg), scripts)
    assert not any(v.startswith("scripts/prereg") for v in violations)
    assert any(v.startswith("scripts/corpus") for v in violations)
