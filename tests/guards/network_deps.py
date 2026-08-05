"""AD-6 guard: core packages must not declare network-capable dependencies.

Scope: every ``packages/*/pyproject.toml`` except ``packages/adapters/*``.
The scanner is intentionally a plain function so the test suite can prove the
guard's FUNCTION on synthetic violating fixtures, not merely its presence
(project convention: a gate must prove the function).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"

BANNED: frozenset[str] = frozenset(
    {"httpx", "requests", "aiohttp", "urllib3", "websockets"}
)


def normalize_dep_name(raw: str) -> str:
    """Reduce a PEP 508 requirement string to a comparable package name."""
    for sep in (";", "[", "=", ">", "<", "!", "~", " "):
        raw = raw.split(sep, 1)[0]
    return raw.strip().lower().replace("_", "-")


def declared_dependencies(pyproject_path: Path) -> set[str]:
    """All dependency names from [project].dependencies and optional-dependencies."""
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    deps: list[str] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        deps.extend(group)
    return {normalize_dep_name(d) for d in deps}


def find_violations(packages_dir: Path) -> list[tuple[Path, str]]:
    """Return (pyproject_path, banned_dep) pairs for non-adapter core packages."""
    violations: list[tuple[Path, str]] = []
    for pyproject in sorted(packages_dir.glob("*/pyproject.toml")):
        if pyproject.parent.name == "adapters":
            continue  # exemption scope: packages/adapters/* only (AD-1/AD-6)
        for dep in sorted(declared_dependencies(pyproject) & BANNED):
            violations.append((pyproject, dep))
    return violations


def all_core_pyprojects() -> list[Path]:
    """Helper for tests: core pyprojects the guard actually covers."""
    return [
        p
        for p in sorted(PACKAGES.glob("*/pyproject.toml"))
        if p.parent.name != "adapters"
    ]
