"""Guard: FR-9 — no judge invocation in validity code paths (static proof)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"

# The validity path for ERBVE: labeling + harness + core-schema + store.
VALIDITY_PACKAGES = ["labeling", "harness", "core-schema", "store"]
JUDGE_IDS = {"openai", "anthropic", "mistralai", "litellm"}
TEXT_MARKERS = re.compile(r"\b(llm[-_ ]?judge|llm[-_ ]?grader|model[-_ ]?graded)\b", re.IGNORECASE)


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


def test_validity_path_has_no_judge_dependencies():
    hits = []
    for pkg in VALIDITY_PACKAGES:
        pp = PACKAGES / pkg / "pyproject.toml"
        if not pp.exists():
            continue
        hits.extend(f"{pkg}: {d}" for d in sorted(_deps(pp) & JUDGE_IDS))
    assert hits == [], "\n".join(hits)


def test_validity_path_has_no_judge_call_references():
    hits = []
    for pkg in VALIDITY_PACKAGES:
        src = PACKAGES / pkg / "src"
        if not src.exists():
            continue
        for f in list(src.rglob("*.py")) + list(src.rglob("*.pyi")):
            marker = TEXT_MARKERS.search(f.read_text())
            if marker:
                hits.append(f"{f.relative_to(REPO_ROOT)}: mentions '{marker.group(0)}'")
    assert hits == [], "judge references in validity modules:\n" + "\n".join(hits)


def test_guard_proves_function(tmp_path):
    fake = tmp_path / "packages"
    (fake / "labeling" / "src").mkdir(parents=True)
    (fake / "labeling" / "pyproject.toml").write_text(
        '[project]\nname="li-labeling"\nversion="0"\nrequires-python=">=3.14"\ndependencies=["openai"]\n'
    )
    (fake / "labeling" / "src" / "x.py").write_text("verdict = llm_judge(out)\n")
    pp = fake / "labeling" / "pyproject.toml"
    assert "openai" in _deps(pp)
    assert TEXT_MARKERS.search((fake / "labeling" / "src" / "x.py").read_text())
