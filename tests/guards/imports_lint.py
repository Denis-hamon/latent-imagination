"""Guard: core packages must not import adapters (AD-1). Proven with a mutation fixture."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"

ADAPTER_MODULES = {"atif_reader", "ci_logs", "harbor_runner", "ots_anchor"}


def _package_of(path: Path, packages_dir: Path) -> tuple[str, bool]:
    """Return (package_dir_name, is_adapter) for a python file under packages/."""
    rel = path.relative_to(packages_dir)
    return rel.parts[0], (rel.parts[0] == "adapters")


def find_import_violations(packages_dir: Path = PACKAGES) -> list[str]:
    violations: list[str] = []
    for mod in sorted(packages_dir.glob("**/*.py")):
        parts = mod.parts
        if "tests" in parts or ".venv" in parts:
            continue
        _stage, is_adapter = _package_of(mod, packages_dir)
        tree = ast.parse(mod.read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for n in names:
                top = n.split(".")[0]
                if top in ADAPTER_MODULES and not is_adapter:
                    violations.append(
                        f"{mod.relative_to(packages_dir)} imports adapter module '{top}'"
                    )
    return violations
