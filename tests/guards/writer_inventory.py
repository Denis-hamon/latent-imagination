"""Guard: write-capable code lives only in owning stages (AD-4). Mutation-proven."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"

# py-to-store write markers that must only appear in owning stage packages.
WRITE_MARKERS = ("write_artifact(", "write_table(", "write_bytes(", "ParquetWriter")

# which packages may contain write markers at all
WRITER_PACKAGES = {
    "store",          # the helper itself
    "traces-ingest",  # canonical snapshots
    "labeling",       # labels + quarantine
    "harness",        # figures + bundles
    "prereg",         # ledger/commit writes
    "publication",    # releases
}


def _pkg_dir_name(path: Path, packages_dir: Path) -> str:
    rel = path.relative_to(packages_dir)
    return rel.parts[0] if rel.parts[0] != "adapters" else rel.parts[1]


def find_unauthorized_writers(packages_dir: Path = PACKAGES) -> list[str]:
    violations: list[str] = []
    for mod in sorted(packages_dir.glob("**/src/**/*.py")):
        pkg = _pkg_dir_name(mod, packages_dir)
        if pkg in WRITER_PACKAGES:
            continue
        text = mod.read_text()
        for marker in WRITE_MARKERS:
            if marker in text:
                violations.append(f"{pkg}: {mod.name} contains write marker '{marker}'")
    return violations
