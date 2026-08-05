"""AD-6 guard tests: no network-capable deps in core packages (adapter-exempt)."""

from __future__ import annotations

from pathlib import Path

from tests.guards.network_deps import all_core_pyprojects, find_violations


def test_core_packages_have_no_network_deps():
    violations = find_violations(Path(__file__).resolve().parents[2] / "packages")
    assert violations == [], (
        "network-capable dependencies must live in packages/adapters/* only: "
        + ", ".join(f"{p.parent.name}: {d}" for p, d in violations)
    )


def test_guard_detects_a_violating_package(tmp_path):
    """Prove the function: a synthetic core package with banned deps must flag,
    while the same dep under packages/adapters/ stays exempt."""
    fixture = tmp_path / "packages"
    payload = fixture / "evil-stage"
    payload.mkdir(parents=True)
    (payload / "pyproject.toml").write_text(
        '[project]\nname = "li-evil"\nversion = "0.1.0"\n'
        'requires-python = ">=3.14"\ndependencies = ["httpx>=0.27", "requests"]\n'
    )
    adapter = fixture / "adapters" / "edge"
    adapter.mkdir(parents=True)
    (adapter / "pyproject.toml").write_text(
        '[project]\nname = "li-edge"\nversion = "0.1.0"\n'
        'requires-python = ">=3.14"\ndependencies = ["httpx"]\n'
    )
    violations = {(str(p.parent.name), d) for p, d in find_violations(fixture)}
    assert violations == {("evil-stage", "httpx"), ("evil-stage", "requests")}


def test_guard_covers_every_core_package():
    """The guard must see all 12 stage packages (no silent skip of the tree)."""
    assert len(all_core_pyprojects()) == 12
