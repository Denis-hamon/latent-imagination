"""Act II delta computation (story 6.2, FR-10): both deltas under Act I's
aggregation discipline, OQ-4 consulted mechanically.

- Aggregation: macro-per-task is the claim line; pooled micro printed under
  (act1-design/design.toml [aggregation]).
- Tolerance: replay_t2_pp from the same sealed file.
- Publish-worthy minimum (OQ-4): read from the sealed decision.toml
  [publishable_delta] — NOT a parameter; the hash of that file is cited in the
  artifact's inputs (AD-13).
- Verdict text: the pre-anchored templates in governance/probe-design/
  verdict-templates/ render it (win/null), never ad-hoc prose.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from core_schema.errors import SchemaError


def _load_pp_minimum(decision_toml: Path) -> tuple[float, str]:
    from hashlib import sha256

    raw = Path(decision_toml).read_bytes()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
        v = float(data["publishable_delta"]["minimum_publishable_pp"])
    except FileNotFoundError as exc:
        raise SchemaError("LI-HARNESS-020", "decision.toml missing (OQ-4 unreadable)", {}) from exc
    except (KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise SchemaError("LI-HARNESS-020", "OQ-4 publishable minimum unreadable", {}) from exc
    if v <= 0:
        raise SchemaError("LI-HARNESS-020", "OQ-4 minimum must be positive", {"got": v})
    return v, sha256(raw).hexdigest()


def _load_tolerance(design_toml: Path) -> float:
    try:
        data = tomllib.loads(Path(design_toml).read_bytes().decode("utf-8"))
        v = float(data["tolerances"]["replay_t2_pp"])
    except FileNotFoundError as exc:
        raise SchemaError("LI-HARNESS-020", "act1 design.toml missing", {}) from exc
    except (KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise SchemaError("LI-HARNESS-020", "replay tolerance unreadable", {}) from exc
    return v


def _macro(series_points: list[dict]) -> float:
    """Act I's claim-line aggregation: mean of per-series macro rates."""
    if not series_points:
        raise SchemaError("LI-HARNESS-020", "empty series — no claim line", {})
    return sum(p["macro_rate"] for p in series_points) / len(series_points)


def compute_deltas(
    act1_points: list[dict],
    act2_points: list[dict],
    *,
    decision_toml: Path,
    design_toml: Path,
) -> dict:
    """Paired per-series deltas + claim lines + mechanical OQ-4 verdict.

    Point shape (harness figures): {family, generation, macro_rate, micro_rate,
    total_attempts, total_false_starts, n_tasks, mean_time_to_valid_s?}.
    """
    if not act2_points:
        raise SchemaError("LI-HARNESS-020", "no Act II points", {})
    key = lambda p: (p["family"], p["generation"])
    a1 = {key(p): p for p in act1_points}
    a2 = {key(p): p for p in act2_points}
    missing = sorted(set(a2) - set(a1))
    if missing:
        raise SchemaError("LI-HARNESS-020", "Act II series without an Act I pin", {"keys": missing})

    per_series = []
    for k in sorted(a2):
        b, a = a2[k], a1[k]
        row = {
            "family": k[0], "generation": k[1],
            "erbve_delta_pp": (a["macro_rate"] - b["macro_rate"]) * 100.0,  # >0 = fewer false starts
            "act1_macro": a["macro_rate"], "act2_macro": b["macro_rate"],
            "act2_attempts": b["total_attempts"],
            "act1_attempts": a["total_attempts"],
        }
        for field, label in (("mean_time_to_valid_s", "ttv_delta_s"),):
            if field in a and field in b:
                row[label] = b[field] - a[field]
        per_series.append(row)

    d_erbve = (_macro(act1_points) - _macro(act2_points)) * 100.0
    ttv = None
    if all("ttv_delta_s" in r for r in per_series) and per_series:
        a1m = sum(a1[k]["mean_time_to_valid_s"] for k in a2) / len(a2)
        a2m = sum(a2[k]["mean_time_to_valid_s"] for k in a2) / len(a2)
        ttv = a2m - a1m

    minimum_pp, decision_hash = _load_pp_minimum(decision_toml)
    tol_pp = _load_tolerance(design_toml)
    material = d_erbve >= minimum_pp  # mechanical: ≥ → material-reduction claim
    return {
        "claim_line": {
            "erbve_delta_pp": round(d_erbve, 4),
            "time_to_valid_delta_s": None if ttv is None else round(ttv, 3),
            "aggregation": "macro_per_task (claim line; pooled micro printed under)",
        },
        "per_series": per_series,
        "oq4": {"minimum_publishable_pp": minimum_pp, "met": material,
                 "verdict": "material-reduction" if material else "below-threshold-measurement-only"},
        "tolerance_pp": tol_pp,
        "_citations": {"decision_toml_sha256": decision_hash},
    }


def render_verdict(deltas: dict, templates_dir: Path) -> str:
    """Pre-anchored templates only: win.md / null.md."""
    name = "win.md" if deltas["oq4"]["met"] else "null.md"
    try:
        template = (Path(templates_dir) / name).read_text()
    except FileNotFoundError as exc:
        raise SchemaError("LI-HARNESS-020", f"verdict template missing ({name})", {}) from exc
    out = template
    out = out.replace("{delta}", f"{deltas['claim_line']['erbve_delta_pp']:+.2f}")
    ci = deltas["claim_line"].get("delta_ci", "n/a")
    margin = "met" if deltas["oq4"]["met"] else "below the minimum"
    return out.replace("{delta_ci}", str(ci)).replace("{margin}", margin)
