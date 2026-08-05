"""AD-6 guard tests: no network-capable deps in core packages (adapter-exempt)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.guards.network_deps import (
    GuardError,
    check_member_conventions,
    find_violations,
    iter_core_pyprojects,
)

REPO_PACKAGES = Path(__file__).resolve().parents[2] / "packages"


def _write(root: Path, rel: str, deps: str) -> None:
    pkg = root / rel
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "pyproject.toml").write_text(
        f'[project]\nname = "li-x"\nversion = "0.1.0"\n'
        f'requires-python = ">=3.14"\n{deps}\n'
    )


def test_core_packages_have_no_network_deps():
    violations = find_violations(REPO_PACKAGES)
    assert violations == [], (
        "network-capable dependencies must live in packages/adapters/* only: "
        + ", ".join(f"{p.relative_to(REPO_PACKAGES)}: {d}" for p, d in violations)
    )


def test_core_violation_flags_every_declared_form(tmp_path):
    """httpx in deps, requests in optional-dependencies, aiohttp in a dev
    dependency-group of a member: all three must flag."""
    packages = tmp_path / "packages"
    _write(packages, "evil-a", 'dependencies = ["httpx[http2]>=0.27"]')
    _write(
        packages,
        "evil-b",
        'dependencies = []\n[project.optional-dependencies]\nx = ["requests"]\n',
    )
    _write(
        packages,
        "evil-c",
        'dependencies = []\n[dependency-groups]\ndev = ["aiohttp"]\n',
    )
    found = {(str(p.parent.name), d) for p, d in find_violations(packages)}
    assert found == {
        ("evil-a", "httpx"),
        ("evil-b", "requests"),
        ("evil-c", "aiohttp"),
    }


def test_adapter_exemption_actually_filters_scanned_packages(tmp_path):
    """Mutation-resistant proof: with the exemption OFF, the adapter flags;
    with it ON, it does not. Deleting the branch breaks this test."""
    packages = tmp_path / "packages"
    _write(packages, "adapters/deep-runner", 'dependencies = ["httpx"]')
    assert find_violations(packages) == []
    assert find_violations(packages, exempt_adapters=False) != []


def test_normalize_bypass_forms_flag(tmp_path):
    """Leading whitespace and spaceless direct refs must not slip through."""
    packages = tmp_path / "packages"
    _write(packages, "ws-sneak", 'dependencies = ["  websockets"]')
    _write(packages, "url-sneak", 'dependencies = ["openai@ git+https://github.com/openai/openai-python"]')
    found = {(str(p.parent.name), d) for p, d in find_violations(packages)}
    assert ("ws-sneak", "websockets") in found
    assert ("url-sneak", "openai") in found


def test_invalid_dependency_strings_flag(tmp_path):
    """Empty or marker-only entries are violations, not silent passes."""
    packages = tmp_path / "packages"
    _write(packages, "broken", 'dependencies = ["", "; python_version < \'4\'"]')
    found = find_violations(packages)
    assert any(d == "<unparseable dependency string>" for _, d in found)


def test_malformed_pyproject_fails_loud(tmp_path):
    packages = tmp_path / "packages"
    pkg = packages / "corrupt"
    pkg.mkdir(parents=True)
    (pkg / "pyproject.toml").write_text("[project\nnot toml")
    with pytest.raises(GuardError, match="corrupt"):
        find_violations(packages)


def test_member_conventions_enforced_on_real_tree():
    """Per-package convention check, replacing the bare count tripwire:
    dist name li-<dir>, module-name == snake(dir), src/<module>/ exists."""
    problems: list[str] = []
    for pyproject in iter_core_pyprojects(REPO_PACKAGES):
        problems.extend(check_member_conventions(pyproject))
    assert problems == [], "\n".join(problems)
