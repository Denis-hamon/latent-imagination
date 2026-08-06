"""Act II delta computation (story 6.2 + CR, FR-10): Act I's TRUE aggregation
discipline, sealed inputs, artifact-grade output.

- Claim-line statistic: POOLED macro-per-task (Σ rate_i·n_i / Σ n_i) — Act I's
  pre-registered statistic; "never a mean of family means" (C1 fix).
- Series sets must be IDENTICAL across acts, each key unique — the delta
  compares like for like or refuses (LI-HARNESS-020).
- Executions-per-task delta is always computable from attempts/n_tasks;
  time-to-valid delta reports ONLY with disclosed coverage (a field Act I
  production points never carried — honesty over theater).
- OQ-4 from the sealed decision.toml; design tolerance from act1-design; both
  sha256-cited. Verdicts render through governance/act2/verdict-templates/
  (anchored in advance per 6.4), NEVER the probe's branch templates.
"""

from __future__ import annotations

import json
import math
import tempfile
import tomllib
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError
from store.emit import compute_store_version, write_artifact

from harness.act2_delta_pipeline import AGGREGATION_NOTE, CI_STATUS, INCLUSIVITY_NOTE

_REQ = ("family", "generation", "macro_rate", "total_attempts", "n_tasks")


def _load_sealed(path: Path, table: list[str], expect=float) -> tuple[float, str]:
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError as exc:
        raise SchemaError("LI-HARNESS-020", "sealed file missing", {"path": str(path)}) from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
        node = data
        for t in table:
            node = node[t]
        v = float(node)
    except (KeyError, TypeError, ValueError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-HARNESS-020", "sealed value unreadable", {"path": str(path)}) from exc
    if not math.isfinite(v) or v <= 0:
        raise SchemaError("LI-HARNESS-020", "sealed value must be finite and positive", {"got": v})
    return v, sha256(raw).hexdigest()


def _check(points: list[dict], what: str) -> None:
    seen: set[tuple] = set()
    for p in points:
        for f in _REQ:
            if f not in p:
                raise SchemaError("LI-HARNESS-020", f"{what} point missing {f}", {"point": p})
        if not isinstance(p["macro_rate"], (int, float)) or isinstance(p["macro_rate"], bool):
            raise SchemaError("LI-HARNESS-020", f"{what} macro_rate not numeric", {})
        if not math.isfinite(float(p["macro_rate"])):
            raise SchemaError("LI-HARNESS-020", f"{what} macro_rate non-finite", {})
        k = (p["family"], p["generation"])
        if k in seen:
            raise SchemaError("LI-HARNESS-020", f"{what} duplicate series key {k}", {})
        seen.add(k)
        n = p["n_tasks"]
        if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
            raise SchemaError("LI-HARNESS-020", f"{what} n_tasks must be a positive int", {})


def _pooled_macro(points: list[dict]) -> float:
    """Act I's pre-registered statistic: pooled over tasks (rate_i·n_i summed)."""
    return sum(p["macro_rate"] * p["n_tasks"] for p in points) / sum(p["n_tasks"] for p in points)


def _exec_per_task(points: list[dict]) -> float:
    return sum(p["total_attempts"] for p in points) / sum(p["n_tasks"] for p in points)


def compute_deltas(
    act1_points: list[dict],
    act2_points: list[dict],
    *,
    decision_toml: Path,
    design_toml: Path,
) -> dict:
    _check(act1_points, "act1")
    _check(act2_points, "act2")
    if not act2_points:
        raise SchemaError("LI-HARNESS-020", "no Act II points", {})
    k1 = {(p["family"], p["generation"]) for p in act1_points}
    k2 = {(p["family"], p["generation"]) for p in act2_points}
    if k1 != k2:
        raise SchemaError("LI-HARNESS-020", "series sets differ — pairs must be exact",
                          {"only_act1": sorted(k1 - k2), "only_act2": sorted(k2 - k1)})

    a1 = {(p["family"], p["generation"]): p for p in act1_points}
    a2 = {(p["family"], p["generation"]): p for p in act2_points}
    per_series = []
    ttv_have = 0
    for k in sorted(a2):
        b, a = a2[k], a1[k]
        row = {
            "family": k[0], "generation": k[1],
            "erbve_delta_pp": (a["macro_rate"] - b["macro_rate"]) * 100.0,
            "act1_macro": a["macro_rate"], "act2_macro": b["macro_rate"],
            "exec_delta_per_task": (b["total_attempts"] / b["n_tasks"]) - (a["total_attempts"] / a["n_tasks"]),
            "n_tasks": b["n_tasks"],
        }
        if "mean_time_to_valid_s" in a and "mean_time_to_valid_s" in b:
            row["ttv_delta_s"] = b["mean_time_to_valid_s"] - a["mean_time_to_valid_s"]
            ttv_have += 1
        per_series.append(row)

    d_erbve = (_pooled_macro(act1_points) - _pooled_macro(act2_points)) * 100.0
    exec_delta = _exec_per_task(act2_points) - _exec_per_task(act1_points)
    ttv_d = None
    if ttv_have == len(a2):  # disclosed coverage only; no partial silent mean
        n1 = sum(a1[k]["n_tasks"] for k in a2)
        ttv_d = (
            sum(a2[k]["mean_time_to_valid_s"] * a2[k]["n_tasks"] for k in a2)
            - sum(a1[k]["mean_time_to_valid_s"] * a1[k]["n_tasks"] for k in a2)
        ) / n1

    minimum_pp, decision_hash = _load_sealed(decision_toml, ["publishable_delta", "minimum_publishable_pp"])
    tol_pp, design_hash = _load_sealed(design_toml, ["tolerances", "replay_t2_pp"])
    material = d_erbve >= minimum_pp  # sealed inclusivity = "inclusive"
    return {
        "claim_line": {
            "erbve_delta_pp": d_erbve,
            "exec_per_task_delta": exec_delta,
            "time_to_valid_delta_s": ttv_d,
            "ttv_coverage": f"{ttv_have}/{len(a2)} paired series",
            "aggregation": AGGREGATION_NOTE,
            "delta_ci": None,
            "ci_status": CI_STATUS,
        },
        "per_series": per_series,
        "oq4": {"minimum_publishable_pp": minimum_pp, "met": material,
                 "verdict": "material-reduction" if material else "below-threshold",
                 "inclusivity": INCLUSIVITY_NOTE},
        "tolerance_pp": tol_pp,
        "_citations": {"decision_toml_sha256": decision_hash, "design_toml_sha256": design_hash},
    }


def render_verdict(deltas: dict, templates_dir: Path) -> str:
    """Act II's OWN pre-anchored templates (governance/act2/verdict-templates/) —
    never the probe's branch prose. Every placeholder must substitute."""
    name = "material-reduction.md" if deltas["oq4"]["met"] else "below-threshold.md"
    try:
        template = (Path(templates_dir) / name).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SchemaError("LI-HARNESS-020", f"verdict template missing ({name})", {}) from exc
    cl = deltas["claim_line"]
    ttv = cl["time_to_valid_delta_s"]
    out = (template
           .replace("{delta}", f"{cl['erbve_delta_pp']:+.2f}")
           .replace("{exec_delta}", f"{cl['exec_per_task_delta']:+.3f}")
           .replace("{ttv}", "n/a (no paired ttv source)" if ttv is None else f"{ttv:+.3f}s")
           .replace("{minimum}", f"{deltas['oq4']['minimum_publishable_pp']:.1f}")
           .replace("{chain}", deltas["_citations"]["decision_toml_sha256"][:16] + "…"))
    import re as _re

    leftovers = _re.findall(r"\{[a-z_]+\}", out)
    if leftovers:
        raise SchemaError("LI-HARNESS-020", "template placeholders left literal",
                          {"leftovers": leftovers})
    return out


def publish_delta_figure(
    deltas: dict,
    store_root: Path,
    *,
    figure_version: str,
    act1_measure_hash: str,
    campaign_pins_hash: str,
    corpus_version: str,
    code_commit: str,
) -> dict:
    """Figure artifact with the AD-13 inputs block tying BOTH Acts' pins."""
    for name, h in (("act1_measure_hash", act1_measure_hash), ("campaign_pins_hash", campaign_pins_hash),
                    ("code_commit", code_commit)):
        if not isinstance(h, str) or len(h) < 8:
            raise SchemaError("LI-HARNESS-020", "pin citation malformed", {"field": name})
    if not isinstance(corpus_version, str) or not corpus_version.startswith("corpus-v"):
        raise SchemaError("LI-HARNESS-020", "corpus_version citation malformed", {})
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "delta.json"
        f.write_text(json.dumps(deltas, indent=1, sort_keys=True) + "\n")
        inputs = {
            "store_snapshot": compute_store_version(store_root),
            "ruleset_version": deltas["_citations"]["decision_toml_sha256"],
            "design_toml_sha256": deltas["_citations"]["design_toml_sha256"],
            "code_commit": code_commit,
            "seeds": {},
            "corpus_version": corpus_version,
            "act1_measure_hash": act1_measure_hash,
            "act2_campaign_pins_hash": campaign_pins_hash,
        }
        res = write_artifact(
            "harness", "figure", "act2-delta", figure_version, [f], inputs, store_root,
        )
    return res.manifest
