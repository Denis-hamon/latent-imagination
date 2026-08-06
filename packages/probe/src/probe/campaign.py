"""Act II campaign pins (story 6.1, FR-10): byte-identical task set + pinned
agents + the advisory module — assembled from the sealed surfaces, cited by
content hash, never re-derived.

Honesty note (2026-08-06 posture): the module slot is the ADVISORY baseline
(sub-bar, branch iii). A run manifest demanding a module pin before the
advisory artifact is re-exported FAILS — pending is policy, not a number.
"""

from __future__ import annotations

import json
import tomllib
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError

MODULE_PENDING = "pending-reexport"  # runs must not start on a pending pin (LI-PROBE-003)


def _sha(p: Path) -> str:
    try:
        return sha256(Path(p).read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise SchemaError("LI-PROBE-003", "campaign pin source missing", {"path": str(p)}) from exc


def _read_toml(p: Path) -> dict:
    try:
        return tomllib.loads(Path(p).read_bytes().decode("utf-8"))
    except FileNotFoundError as exc:
        raise SchemaError("LI-PROBE-003", "campaign pin source missing", {"path": str(p)}) from exc
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-PROBE-003", "pin source unparseable", {"path": str(p)}) from exc


def build_campaign_pins(repo_root: Path, *, observed_models: list[dict]) -> dict:
    """Assemble campaign-pins-v1 from governance/act1-design + probe-design.

    `observed_models`: from the Act I field measurement — each entry
    {model, vendor_generation, evidence_file}; a pin without evidence fails.
    """
    root = Path(repo_root)
    act1 = root / "governance" / "act1-design"
    design_p, tasks_p = act1 / "design.toml", act1 / "tasks.toml"
    design = _read_toml(design_p)
    _ = _read_toml(tasks_p)  # parse-fail = coded; the hash is the teeth
    decision_p = root / "governance" / "probe-design" / "decision.toml"

    agents = []
    for m in observed_models:
        ev = m.get("evidence_file")
        if not ev or not Path(ev).is_file():
            raise SchemaError("LI-PROBE-003", "agent pin without evidence file",
                              {"model": m.get("model")})
        agents.append({
            "model": m["model"],
            "vendor_generation": m.get("vendor_generation"),
            "evidence": {"file": str(ev), "sha256": _sha(Path(ev))},
            "verified_at": m.get("verified_at"),
            "mismatch_policy": "re-collect the un-augmented arm alongside, disclose the drift in the paired publication",
        })
    families = {a["vendor_generation"] for a in agents}
    required = int(design.get("subset", {}).get("families_required", 3)) if "subset" in design else 3
    if len(families) < required:
        raise SchemaError("LI-PROBE-003", "fewer distinct families than FR-6 requires",
                          {"have": sorted(families), "required": required})

    payload = {
        "campaign": "act2-intervention",
        "task_set": {"design": str(design_p), "design_sha256": _sha(design_p),
                     "tasks": str(tasks_p), "tasks_sha256": _sha(tasks_p)},
        "protocol": {"decision": str(decision_p), "decision_sha256": _sha(decision_p)},
        "agents": agents,
        "module": {"advisory_predictor_hash": MODULE_PENDING,
                   "posture": "sub-bar advisory baseline (branch iii) — measured, NOT certified",
                   "policy": "re-export via probe.arms.baseline_export before the window; runs refuse on pending"},
    }
    return payload


def write_campaign_pins(payload: dict, out_path: Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(out_path)


def require_module_pin(payload: dict) -> str:
    """A run manifest cannot mint on a pending module pin."""
    h = (payload.get("module") or {}).get("advisory_predictor_hash")
    if not isinstance(h, str) or h == MODULE_PENDING or len(h) != 64:
        raise SchemaError("LI-PROBE-003", "module pin pending — re-export first", {"got": h})
    return h
