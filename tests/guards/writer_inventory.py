"""Guard: write-capable code lives only in owning stages (AD-4). Mutation-proven.

Scope notes:
- AD-4 polices canonical-store writes. Adapters are EXEMPT — their job is
  landing-zone deposits (occurrence artifacts), which is not the protected
  surface. Compile-time ownership matters at the canonical store, not the landing.
- scripts/ ARE scanned (story 4.1, closes the deferred-work Epic-1 entry that
  noted them out of scope): a script may not hold write markers aimed at store
  paths — EXCEPT `scripts/prereg/`, the sanctioned ceremony surface whose
  ledger/proof/release writes are occurrence records by design (story 2.6)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"
SCRIPTS = REPO_ROOT / "scripts"

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
    "corpus",         # corpus item-sets (AD-4 row, story 4.1)
    "adapters",       # landing-zone deposits (occurrence artifacts)
}

# scripts subtrees whose store-aimed writes are sanctioned ceremony surfaces:
# prereg = ceremonies (story 2.6 design); act1 = Act-I field-run/campaign
# orchestration writing occurrence-class outputs under a caller-passed store root.
SCRIPT_SANCTIONED = ("prereg", "act1")


def _pkg_dir_name(path: Path, packages_dir: Path) -> str:
    rel = path.relative_to(packages_dir)
    return rel.parts[0] if rel.parts[0] != "adapters" else "adapters"


_STORE_TARGETS = ("store_root", "canonical/", "labels/", "quarantine/", "figures/", "bundles/", "prereg/", "releases/")


def _scan_tree(root: Path, pattern: str, classify, violations: list[str]) -> None:
    for mod in sorted(root.glob(pattern)):
        verdict = classify(mod)
        if verdict is None:
            continue  # sanctioned / exempt
        text = mod.read_text()
        for marker in WRITE_MARKERS:
            if marker in text and any(t in text for t in _STORE_TARGETS):
                violations.append(f"{verdict}: {mod.name} contains write marker '{marker}' aimed at a store path")


def find_unauthorized_writers(packages_dir: Path = PACKAGES, scripts_dir: Path = SCRIPTS) -> list[str]:
    violations: list[str] = []

    def pkg_classify(mod: Path) -> str | None:
        pkg = _pkg_dir_name(mod, packages_dir)
        return None if pkg in WRITER_PACKAGES else f"{pkg}"

    _scan_tree(packages_dir, "**/src/**/*.py", pkg_classify, violations)

    if scripts_dir.is_dir():
        def script_classify(mod: Path) -> str | None:
            rel = mod.relative_to(scripts_dir)
            return None if rel.parts[0] in SCRIPT_SANCTIONED else f"scripts/{rel.parts[0]}"

        _scan_tree(scripts_dir, "**/*.py", script_classify, violations)
    return violations
