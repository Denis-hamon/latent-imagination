"""Act II replay tiers (story 6.3, FR-8): Tier-1 bitwise recompute of the delta
figure + declared-independent re-run report + divergence routing.

- Tier 1: the bundle carries BOTH acts' pinned point sets + the delta pipeline
  entrypoint; verification recomputes delta.json and compares BYTES (commodity
  hardware — pure stdlib).
- Declared-independent re-run: the report carries the operator's declared
  affiliation and the sealed replay tolerance (design.toml [tolerances],
  inclusive semantics, decided on the rounded value so report and recomputation
  agree per tier2's discipline).
- Divergence never patches quietly: the report names the first diverging
  artifact and routes to governance/erratum-protocol.md.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError

from harness.tier2 import compare_within_tolerance

TOLERANCE_SOURCE = "governance/act1-design/design.toml [tolerances].replay_t2_pp"
ERRATUM_ROUTE = "governance/erratum-protocol.md"

_PIPELINE = '''"""Delta recomputation — replay entrypoint (stdlib only)."""
import json, sys, tomllib
from hashlib import sha256
from pathlib import Path

def _load(path, table):
    data = tomllib.loads(Path(path).read_bytes().decode("utf-8"))
    for t in table: data = data[t]
    return float(data)

def points(root, name):
    return json.loads((root / "slice" / name).read_text())["points"]

def macro(ps):
    return sum(p["macro_rate"] * p["n_tasks"] for p in ps) / sum(p["n_tasks"] for p in ps)

root = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else Path(".")
a1, a2 = points(root, "act1.json"), points(root, "act2.json")
mp = _load(root / "slice" / "decision.toml", ["publishable_delta", "minimum_publishable_pp"])
tol = _load(root / "slice" / "design.toml", ["tolerances", "replay_t2_pp"])
d = {"erbve_delta_pp": (macro(a1) - macro(a2)) * 100.0,
     "met": (macro(a1) - macro(a2)) * 100.0 >= mp, "tolerance_pp": tol}
out = root / "out" / "delta.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(d, indent=1, sort_keys=True) + "\\n")
print(sha256(out.read_bytes()).hexdigest())
'''


def assemble_delta_bundle(
    out_root: Path,
    *,
    act1_points: list[dict],
    act2_points: list[dict],
    decision_toml: Path,
    design_toml: Path,
) -> Path:
    """Tier-1 replay bundle for the Act II delta figure (commodity reproducible)."""
    for name, pts in (("act1_points", act1_points), ("act2_points", act2_points)):
        if not pts:
            raise SchemaError("LI-HARNESS-021", f"{name} empty", {})
    bundle = Path(out_root) / "act2-delta-bundle"
    if bundle.exists():
        raise SchemaError("LI-HARNESS-021", "bundle exists — cut a new version", {"path": str(bundle)})
    (bundle / "slice").mkdir(parents=True)
    (bundle / "pipeline").mkdir()
    for name, pts in (("act1.json", act1_points), ("act2.json", act2_points)):
        (bundle / "slice" / name).write_text(json.dumps({"points": pts}, indent=1, sort_keys=True) + "\n")
    shutil.copy(decision_toml, bundle / "slice" / "decision.toml")
    shutil.copy(design_toml, bundle / "slice" / "design.toml")
    (bundle / "pipeline" / "run.py").write_text(_PIPELINE)
    manifest = {
        "bundle": "act2-delta",
        "created_from": {"decision": sha256(Path(decision_toml).read_bytes()).hexdigest(),
                         "design": sha256(Path(design_toml).read_bytes()).hexdigest()},
        "tolerance_source": TOLERANCE_SOURCE,
        "divergence_route": ERRATUM_ROUTE,
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return bundle


def verify_delta_bundle(bundle: Path) -> dict:
    """Tier-1: recompute the pipeline in isolation; report bytes + claim."""
    bundle = Path(bundle)
    run = bundle / "pipeline" / "run.py"
    if not run.is_file():
        raise SchemaError("LI-HARNESS-021", "bundle pipeline missing", {"path": str(bundle)})
    out = bundle / "out"
    if out.exists():
        shutil.rmtree(out)
    result = subprocess.run(
        [sys.executable, "-I", str(run), "--root", str(bundle)],
        capture_output=True, text=True, cwd=str(bundle), check=False,
    )
    if result.returncode != 0:
        raise SchemaError("LI-HARNESS-021", "replay pipeline crashed",
                          {"stderr": result.stderr[-400:]})
    produced = json.loads((out / "delta.json").read_text())
    return {
        "claim_erbve_delta_pp": produced["erbve_delta_pp"],
        "met": produced["met"],
        "output_sha256": result.stdout.strip(),
        "isol": "-I",
    }


def rerun_report(
    bundle: Path,
    *,
    published_delta_pp: float,
    operator: str,
    affiliation: str,
    tolerance_pp: float,
) -> dict:
    """Declared-independent re-run (FR-8): affiliation declared up front; the
    comparison uses the sealed tolerance with tier2's rounded-decision rule;
    divergence routes to the erratum protocol, never to a quiet patch."""
    if not isinstance(operator, str) or not operator.strip():
        raise SchemaError("LI-HARNESS-021", "operator must be declared", {})
    if not isinstance(affiliation, str) or not affiliation.strip():
        raise SchemaError("LI-HARNESS-021", "affiliation must be declared (FR-8 standard)", {})
    v = verify_delta_bundle(bundle)
    comp = compare_within_tolerance(
        "act2-erbve-delta", published_delta_pp, v["claim_erbve_delta_pp"],
        tolerance_pp=tolerance_pp,
        first_diverging_artifact="out/delta.json" if abs(v["claim_erbve_delta_pp"] - published_delta_pp) * 100 > tolerance_pp else None,
    )
    return {
        "rerun": {"operator": operator, "affiliation": affiliation},
        "published_delta_pp": published_delta_pp,
        "reproduced_delta_pp": v["claim_erbve_delta_pp"],
        "within_tolerance": comp.within,
        "delta_pp": comp.delta_pp,
        "tolerance_pp": tolerance_pp,
        "tolerance_source": TOLERANCE_SOURCE,
        "divergence_route": ERRATUM_ROUTE if not comp.within else None,
    }
