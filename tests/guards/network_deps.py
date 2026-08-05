"""AD-6 guard: core packages must not declare network-capable dependencies.

Scope: every pyproject.toml under ``packages/``, recursively, EXCEPT packages
nested beneath a ``adapters`` component (``packages/adapters/*``). The guard
covers direct dependencies, optional-dependencies, AND dependency-groups;
scope is the *declared* dependency set (the transitive/uv.lock closure scan
is deferred to the Story 1.5 dependency-scan layer — see deferred-work.md).

The denylist is kept intentionally broad for a repository whose core must
never make network calls (AD-6) — including LLM client SDKs, the most likely
drift path in an agent-interceptor project.

The scanner is written so the suite can prove the guard's FUNCTION on
synthetic fixtures (project convention: a gate must prove the function),
including that the adapter exemption really filters scanned packages.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"

BANNED: frozenset[str] = frozenset(
    {
        # raw HTTP / WebSocket transports
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        "websockets",
        "websocket-client",
        # other network stacks / cloud clients
        "grpcio",
        "curl-cffi",
        "pycurl",
        "paramiko",
        "python-socketio",
        "boto3",
        # LLM client SDKs — the interceptor project's most likely drift path
        "openai",
        "anthropic",
        "mistralai",
    }
)


class GuardError(Exception):
    """Configuration/parsing failure the guard must surface, never swallow."""


def normalize_dep_name(raw: str) -> str:
    """Reduce a PEP 508 requirement string to a comparable package name.

    Handles whitespace, extras, markers, version specifiers and direct
    references (``name@url``, with or without spaces).
    """
    raw = raw.strip()
    for sep in (";", "[", "@", "=", ">", "<", "!", "~", " "):
        raw = raw.split(sep, 1)[0]
    return raw.strip().lower().replace("_", "-")


def declared_dependencies(pyproject_path: Path) -> set[str]:
    """All dependency names from dependencies, optional-dependencies and
    dependency-groups tables. Raises GuardError with the path on bad TOML."""
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise GuardError(f"cannot parse {pyproject_path}: {exc}") from exc
    project = data.get("project", {})
    deps: list[str] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        deps.extend(group)
    for group in data.get("dependency-groups", {}).values():
        deps.extend(group)
    return {normalize_dep_name(d) for d in deps}


def _is_adapter(pyproject_path: Path, packages_dir: Path) -> bool:
    """An adapter is any package nested under a ``adapters`` directory."""
    rel = pyproject_path.relative_to(packages_dir)
    return "adapters" in rel.parts[:-1]


def iter_all_pyprojects(packages_dir: Path) -> list[Path]:
    """Every member pyproject under packages/, at ANY depth (no silent skips)."""
    return sorted(packages_dir.glob("**/pyproject.toml"))


def find_violations(
    packages_dir: Path,
    *,
    exempt_adapters: bool = True,
) -> list[tuple[Path, str]]:
    """Return (pyproject_path, banned_dep) pairs for covered packages.

    With ``exempt_adapters=False`` the adapter exemption is switched off —
    used by the test suite to prove the exemption actually filters scanned
    packages (mutation-resistant proof of function).
    """
    violations: list[tuple[Path, str]] = []
    for pyproject in iter_all_pyprojects(packages_dir):
        if exempt_adapters and _is_adapter(pyproject, packages_dir):
            continue
        declared = declared_dependencies(pyproject)
        for dep in sorted(declared & BANNED):
            violations.append((pyproject, dep))
        if "" in declared or any(d is None for d in declared):
            violations.append((pyproject, "<unparseable dependency string>"))
    return violations


def iter_core_pyprojects(packages_dir: Path) -> list[Path]:
    """Non-adapter pyprojects the guard covers (any depth)."""
    return [
        p for p in iter_all_pyprojects(packages_dir) if not _is_adapter(p, packages_dir)
    ]


def check_member_conventions(pyproject_path: Path) -> list[str]:
    """Member-shape conventions: dist name, module-name override, src layout.

    For directory ``packages/<kebab>`` (or ``packages/adapters/<kebab>``):
    distribution name must be ``li-<kebab>``, the uv_build module-name must be
    the snake_case of the dir name, and ``src/<module>/`` must exist.
    """
    problems: list[str] = []
    dirname = pyproject_path.parent.name
    expected_dist = f"li-{dirname}"
    expected_module = dirname.replace("-", "_")
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dist = data.get("project", {}).get("name")
    if dist != expected_dist:
        problems.append(f"{dirname}: dist name must be '{expected_dist}', got {dist!r}")
    module = (
        data.get("tool", {}).get("uv", {}).get("build-backend", {}).get("module-name")
    )
    if module != expected_module:
        problems.append(
            f"{dirname}: [tool.uv.build-backend] module-name must be '{expected_module}', got {module!r}"
        )
    if not (pyproject_path.parent / "src" / expected_module).is_dir():
        problems.append(f"{dirname}: missing src/{expected_module}/")
    return problems
