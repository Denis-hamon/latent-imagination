"""Proof tests for the AD-1 import lint guard."""

from __future__ import annotations

from tests.guards.imports_lint import find_import_violations


def test_core_never_imports_adapters_on_real_tree():
    violations = find_import_violations()
    assert violations == [], "\n".join(violations)


def test_guard_detects_a_violating_import(tmp_path):
    fake = tmp_path / "packages"
    core = fake / "core-schema" / "src" / "core_schema"
    core.mkdir(parents=True)
    (core / "bad.py").write_text("import ots_anchor\n")
    adapter = fake / "adapters" / "ots-anchor" / "src" / "ots_anchor"
    adapter.mkdir(parents=True)
    (adapter / "ok.py").write_text("import core_schema\n")  # adapters MAY import core
    violations = find_import_violations(fake)
    assert any("bad.py" in v for v in violations)
    assert not any("ok.py" in v for v in violations)
