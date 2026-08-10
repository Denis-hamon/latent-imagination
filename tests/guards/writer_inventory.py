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

# Single source of truth: the package set derives from the store's own table
# (AD-4) — extending one without the other was a real drift source (8.3 CR).
def _writer_packages() -> set[str]:
    from store.emit import WRITERS

    return set(WRITERS) | {"store", "adapters"}


WRITER_PACKAGES = _writer_packages()

# scripts subtrees whose store-aimed writes are sanctioned ceremony surfaces:
# prereg = ceremonies (story 2.6 design); act1 = Act-I field-run/campaign
# orchestration writing occurrence-class outputs under a caller-passed store root;
# probe = the pinned arm-artifact re-export ceremony (Act II, story 6.2 machinery);
# act2 = Act-II pilot campaign orchestration — same occurrence-class landing writes
# as act1 (labels/results under data/landing), never the canonical store.
SCRIPT_SANCTIONED = ("prereg", "act1", "probe", "act2")

# vendored environments are not repo-authored code — scanning their
# site-packages would flag huggingface_hub & co, not our writers.
_SKIP_DIRS = {"venv", ".venv", "node_modules", "__pycache__"}


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
            if any(part in _SKIP_DIRS for part in rel.parts):
                return None
            return None if rel.parts[0] in SCRIPT_SANCTIONED else f"scripts/{rel.parts[0]}"

        _scan_tree(scripts_dir, "**/*.py", script_classify, violations)
    return violations
