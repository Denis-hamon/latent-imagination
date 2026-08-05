"""Guard: gate* packages never gain an LLM client closure (AD-14)."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"

LLM_CLIENTS = {
    "openai",
    "anthropic",
    "mistralai",
    "litellm",
    "langchain",
    "langchain-core",
    "langsmith",
    "instructor",
    "guidance",
}


def _deps(pyproject: Path) -> set[str]:
    data = tomllib.loads(pyproject.read_text())
    deps: list[str] = list(data.get("project", {}).get("dependencies", []))
    for g in data.get("project", {}).get("optional-dependencies", {}).values():
        deps.extend(g)
    for g in data.get("dependency-groups", {}).values():
        deps.extend(g)
    out = set()
    for d in deps:
        d = d.strip()
        for sep in (";", "[", "@", "=", ">", "<", "!", "~", " "):
            d = d.split(sep, 1)[0]
        out.add(d.strip().lower().replace("_", "-"))
    return out


def find_gate_llm_violations(packages_dir: Path = PACKAGES) -> list[str]:
    violations = []
    for pyproject in sorted(packages_dir.glob("**/pyproject.toml")):
        pkg = pyproject.parent.name
        if not pkg.startswith("gate"):
            continue
        hit = _deps(pyproject) & LLM_CLIENTS
        for dep in sorted(hit):
            violations.append(f"{pkg}: declares LLM client '{dep}'")
    return violations
