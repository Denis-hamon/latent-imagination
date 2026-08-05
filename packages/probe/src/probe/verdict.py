"""Verdict engine — mechanical execution of the registered decision.toml.
No manual override exists by construction: verdict = f(metrics, design)."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Verdict:
    branch: str  # "i" | "ii" | "iii"
    reason: str
    shipped: str  # "jepa" | "baseline" | "none"
    values: dict


def _read_design(path: Path) -> dict:
    d = tomllib.loads(Path(path).read_text())
    # flat essentials
    return {
        "bar": d["bar"]["registered_bar"],
        "margin": d["margin"]["min_margin"],
        "cross": d["strictness"]["cross"],
        "margin_met": d["strictness"]["margin_met"],
        "tie": d["strictness"]["tie_at_margin"],
        "branches": {
            "i": d["branches"]["branch_i"],
            "ii": d["branches"]["branch_ii"],
            "iii": d["branches"]["branch_iii"],
        },
    }


def compute_verdict(
    baseline_precision: float,
    jepa_precision: float | None,
    *,
    design_path: Path,
) -> Verdict:
    d = _read_design(design_path)
    bar, margin = d["bar"], d["margin"]

    base_crosses = baseline_precision >= bar
    jepa_crosses = (jepa_precision is not None) and (jepa_precision >= bar)
    margin_met = (jepa_precision is not None) and ((jepa_precision - baseline_precision) >= margin)

    # registered strictness semantics:
    # any arm crossing the bar fires branch i/ii; none fires branch iii
    if jepa_crosses and margin_met:
        return Verdict("i", d["branches"]["i"], "jepa", {
            "bar": bar, "baseline_precision": baseline_precision,
            "jepa_precision": jepa_precision, "margin": margin,
        })
    if not (base_crosses and jepa_precision is not None):
        # baseline below bar, or no jepa result at all → bar unreachable
        return Verdict("iii", d["branches"]["iii"], "none", {
            "bar": bar, "baseline_precision": baseline_precision,
            "jepa_precision": jepa_precision, "margin": margin,
        })
    # someone crosses; margin unmet (incl. tie → baseline)
    return Verdict("ii", d["branches"]["ii"], "baseline", {
        "bar": bar, "baseline_precision": baseline_precision,
        "jepa_precision": jepa_precision, "margin": margin,
    })


def render_verdict_document(verdict: Verdict, *, template_dir: Path, out_path: Path) -> Path:
    """Fill the PRE-ANCHORED template; refuse to render anything else."""
    template = template_dir / {
        "i": "win.md",
        "ii": "null.md",
        "iii": "measurement-only.md",
    }[verdict.branch]
    text = template.read_text()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n\n---\n## Registered values\n\n```json\n" + json.dumps(verdict.values, indent=2) + "\n```\n")
    return out_path
