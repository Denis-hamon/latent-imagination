"""Guard: write-capable code lives only in owning stages (AD-4). Mutation-proven.

Scope note: AD-4 polices canonical-store writes. Adapters are EXEMPT — their job
is landing-zone deposits (occurrence artifacts), which is not the protected
surface. Compile-time ownership matters at the canonical store, not the landing."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"

# py-to-store write markers in owning stage packages. Broad, intentionally
# substring-based — the invariant is "any unauthorized write marker anywhere".
WRITE_MARKERS = (
    "write_artifact(",
    "write_table(",
    "write_bytes(",
    "write_text(",
    "ParquetWriter",
    "copyfile(",
    "copy2(",
    "os.remove(",
)

# which packages may contain write markers at all ("adapters" covers the edge set)
WRITER_PACKAGES = {
    "store",          # the helper itself
    "traces-ingest",  # canonical snapshots
    "labeling",       # labels + quarantine
    "harness",        # figures + bundles
    "prereg",         # ledger/commit writes
    "publication",    # releases
    "adapters",       # landing-zone deposits (occurrence artifacts)
}


def _pkg_dir_name(path: Path, packages_dir: Path) -> str:
    rel = path.relative_to(packages_dir)
    return rel.parts[0] if rel.parts[0] != "adapters" else "adapters"


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
