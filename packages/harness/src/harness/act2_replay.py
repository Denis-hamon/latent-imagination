"""Act II replay tiers (story 6.3 + CR, FR-8): Tier-1 bitwise recompute of the
FULL delta figure + declared-independent re-run that PERSISTS, with the
pre-publication gate.

Discipline (Act I's house pattern, stated in replay_export.py): the bundle
carries a VERBATIM copy of the canonical pipeline
(`act2_delta_pipeline.py` — stdlib-only, commodity hardware); the package-side
`delta.py` is pinned equivalent by a shared-fixture equivalence test (the
anti-drift tripwire). Verification is ANCHORED: produced bytes vs the pinned
expected bytes (the published figure's file), never a self-comparison. The
re-run report is written as a store bundle artifact (occurrence class): it can
ship, and `assemble_act2_release_packet` REFUSES a publication without it.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import store.emit as _store_emit  # noqa: F401  (ownership table visible to guards)
from core_schema.errors import SchemaError
from store.emit import compute_store_version, write_artifact

from harness.tier2 import compare_within_tolerance

CANONICAL_PIPELINE = Path(__file__).resolve().parent / "act2_delta_pipeline.py"
TOLERANCE_SOURCE = "governance/act1-design/design.toml [tolerances].replay_t2_pp"
ERRATUM_ROUTE = "governance/erratum-protocol.md"
_README = """# act2-delta replay bundle (Tier 1)

Commodity re-run: `python pipeline/run.py --root .` → `out/delta.json`.
Verify publishes bytes vs expected/delta.json (the pinned published figure).
No dependencies beyond Python ≥3.11 (stdlib only). Wall time: seconds.
"""


def assemble_delta_bundle(
    out_root: Path,
    *,
    act1_points: list[dict],
    act2_points: list[dict],
    decision_toml: Path,
    design_toml: Path,
    expected_delta_json: Path,
) -> Path:
    """Tier-1 bundle: pinned points + sealed tomls + verbatim canonical pipeline
    + the EXPECTED published figure (the anchor — nothing self-compares)."""
    for name, pts in (("act1_points", act1_points), ("act2_points", act2_points)):
        if not pts:
            raise SchemaError("LI-HARNESS-021", f"{name} empty", {})
    for p, label in ((decision_toml, "decision.toml"), (design_toml, "design.toml"),
                     (expected_delta_json, "expected delta")):
        if not Path(p).is_file():
            raise SchemaError("LI-HARNESS-021", f"bundle source missing: {label}", {"path": str(p)})
    bundle = Path(out_root) / "act2-delta-bundle"
    try:
        (bundle / "slice").mkdir(parents=True)  # atomic-claim: re-run same version fails loud
    except FileExistsError as exc:
        raise SchemaError("LI-HARNESS-021", "bundle exists — cut a new version", {"path": str(bundle)}) from exc
    (bundle / "pipeline").mkdir()
    (bundle / "expected").mkdir()
    for name, pts in (("act1.json", act1_points), ("act2.json", act2_points)):
        (bundle / "slice" / name).write_bytes((json.dumps({"points": pts}, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    shutil.copy(decision_toml, bundle / "slice" / "decision.toml")
    shutil.copy(design_toml, bundle / "slice" / "design.toml")
    shutil.copy(CANONICAL_PIPELINE, bundle / "pipeline" / "run.py")
    shutil.copy(expected_delta_json, bundle / "expected" / "delta.json")
    manifest = {
        "bundle": "act2-delta",
        "python_floor": ">=3.11 (stdlib tomllib)",
        "created_from": {
            "decision_toml_sha256": sha256(Path(decision_toml).read_bytes()).hexdigest(),
            "design_toml_sha256": sha256(Path(design_toml).read_bytes()).hexdigest(),
            "expected_delta_sha256": sha256(Path(expected_delta_json).read_bytes()).hexdigest(),
            "act1_points_sha256": sha256((bundle / "slice" / "act1.json").read_bytes()).hexdigest(),
            "act2_points_sha256": sha256((bundle / "slice" / "act2.json").read_bytes()).hexdigest(),
            "pipeline_sha256": sha256(Path(CANONICAL_PIPELINE).read_bytes()).hexdigest(),
        },
        "tier2_prerequisites": {
            "hardware_floor": "module-enabled predictor re-licensed floor: advisory baseline = CPU stdlib — none",
            "recollection_costs": "vendor-drift re-collection per campaign-plan-v1.md (API budget; R10 pre-registered at the window)",
        },
        "tolerance_source": TOLERANCE_SOURCE,
        "divergence_route": ERRATUM_ROUTE,
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (bundle / "README.md").write_text(_README)
    return bundle


def _bytes_equal(a: Path, b: Path) -> bool:
    return a.read_bytes() == b.read_bytes()


def verify_delta_bundle(bundle: Path) -> dict:
    """ANCHORED Tier-1: produced bytes vs the pinned expected bytes."""
    bundle = Path(bundle)
    for rel, label in (("pipeline/run.py", "pipeline"), ("expected/delta.json", "expected anchor"),
                       ("slice/act1.json", "act1 slice"), ("slice/act2.json", "act2 slice")):
        if not (bundle / rel).is_file():
            raise SchemaError("LI-HARNESS-021", f"bundle incomplete: {label} missing", {})
    out = bundle / "out"
    if out.exists():
        if not out.is_dir():
            raise SchemaError("LI-HARNESS-021", "out path is not a directory (crash residue)", {})
        try:
            shutil.rmtree(out)
        except OSError as exc:
            raise SchemaError("LI-HARNESS-021", "cannot clear prior out/", {"err": str(exc)}) from exc
    result = subprocess.run(
        [sys.executable, "-I", str(bundle / "pipeline" / "run.py"), "--root", str(bundle)],
        capture_output=True, text=True, cwd=str(bundle), check=False, timeout=120,
    )
    if result.returncode != 0:
        raise SchemaError("LI-HARNESS-021", "replay pipeline reported an error",
                          {"stderr": result.stderr[-400:]})
    produced = out / "delta.json"
    if not produced.is_file():
        raise SchemaError("LI-HARNESS-021", "pipeline exited 0 but produced no delta.json", {})
    expected = bundle / "expected" / "delta.json"
    return {
        "produced_sha256": sha256(produced.read_bytes()).hexdigest(),
        "expected_sha256": sha256(expected.read_bytes()).hexdigest(),
        "bitwise_equal": _bytes_equal(produced, expected),
        "isol": "-I + 120s timeout",
    }


def rerun_report(
    bundle: Path,
    *,
    published_delta_pp: float,           # pp — the published claim scale
    operator: str,
    affiliation: str,
    tolerance_pp: float,                 # sealed scale (pp)
    affiliation_disputed: bool = False,  # the second divergence route (FR-8)
) -> dict:
    """Declared-independent re-run: persists as a store bundle artifact.

    Unit contract (CR 6.3): the comparator works in FRACTIONS (its own tests);
    both pp inputs are converted once, here, with the conversion shown."""
    if not isinstance(operator, str) or not operator.strip():
        raise SchemaError("LI-HARNESS-021", "operator must be declared", {})
    if not isinstance(affiliation, str) or not affiliation.strip():
        raise SchemaError("LI-HARNESS-021", "affiliation must be declared (FR-8 standard)", {})
    if not (isinstance(tolerance_pp, (int, float)) and not isinstance(tolerance_pp, bool)
            and math.isfinite(tolerance_pp) and tolerance_pp >= 0):
        raise SchemaError("LI-HARNESS-021", "tolerance must be finite ≥ 0 pp", {"got": tolerance_pp})
    if not (isinstance(published_delta_pp, (int, float)) and math.isfinite(published_delta_pp)):
        raise SchemaError("LI-HARNESS-021", "published delta malformed", {})

    v = verify_delta_bundle(bundle)
    try:
        produced_delta_pp = json.loads((Path(bundle) / "out" / "delta.json").read_text())["claim_line"]["erbve_delta_pp"]
    except (ValueError, KeyError) as exc:
        raise SchemaError("LI-HARNESS-021", "produced delta unreadable", {}) from exc

    # unit bridge: comparator expects fractions; ours are pp
    comp = compare_within_tolerance(
        "act2-erbve-delta", published_delta_pp / 100.0, produced_delta_pp / 100.0,
        tolerance_pp=tolerance_pp,
        first_diverging_artifact="out/delta.json" if not (
            abs(produced_delta_pp - published_delta_pp) <= tolerance_pp) else None,
    )
    routes = []
    if not comp.within:
        routes.append(ERRATUM_ROUTE + " (tolerance breach)")
    if affiliation_disputed:
        routes.append(ERRATUM_ROUTE + " (affiliation dispute)")
    return {
        "rerun": {"operator": operator, "affiliation": affiliation},
        "published_delta_pp": published_delta_pp,
        "reproduced_delta_pp": produced_delta_pp,
        "delta_pp": round(abs(produced_delta_pp - published_delta_pp), 4),
        "tolerance_pp": tolerance_pp,
        "tolerance_source": TOLERANCE_SOURCE,
        "within_tolerance": comp.within if not affiliation_disputed else False,
        "first_diverging_artifact": comp.first_diverging_artifact,
        "bitwise_anchor": {"produced_sha256": v["produced_sha256"],
                            "expected_sha256": v["expected_sha256"],
                            "bitwise_equal": v["bitwise_equal"]},
        "affiliation_disputed": affiliation_disputed,
        "divergence_routes": routes or None,
    }


def persist_rerun_report(report: dict, store_root: Path, *, bundle_dir: Path, code_commit: str) -> dict:
    """The re-run SHIPS: occurrence-class bundle artifact (AD-7 allows the
    timestamp); inputs cite the bundle manifest hash + the verified bytes."""
    bundle_dir = Path(bundle_dir)
    man_p = bundle_dir / "manifest.json"
    if not man_p.is_file():
        raise SchemaError("LI-HARNESS-021", "bundle manifest missing — persist against what?", {})
    with __import__("tempfile").TemporaryDirectory() as tmp:
        f = Path(tmp) / "rerun-report.json"
        f.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        inputs = {
            "store_snapshot": compute_store_version(store_root),
            "ruleset_version": "n/a (occurrence)",
            "code_commit": code_commit,
            "seeds": {},
            "corpus_version": "corpus-v0",
            "bundle_manifest_sha256": sha256(man_p.read_bytes()).hexdigest(),
            "bitwise_anchor": report.get("bitwise_anchor"),
        }
        res = write_artifact("harness", "bundle", "act2-delta-rerun", "v0", [f], inputs, store_root)
    return res.manifest


def assemble_act2_release_packet(packet_dir: Path, *, rerun_report_artifact: Path | None) -> Path:
    """The pre-publication gate (FR-10): no re-run report, no packet."""
    packet_dir = Path(packet_dir)
    packet_dir.mkdir(parents=True, exist_ok=True)
    if rerun_report_artifact is None or not Path(rerun_report_artifact).is_file():
        raise SchemaError(
            "LI-HARNESS-021",
            "declared-independent re-run report is a PRECONDITION of the Act II release "
            "(FR-10) — persist it first (persist_rerun_report)",
            {},
        )
    shutil.copy(rerun_report_artifact, packet_dir / "rerun-report.json")
    return packet_dir
