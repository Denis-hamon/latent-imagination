"""Act II campaign pins (story 6.1 + CR, FR-10): byte-identical task set +
pinned agents + advisory module — assembled from the sealed surfaces.

Hard-won rules from the review:
- the family floor value is read from tasks.toml's [subset] — the ACTUAL sealed
  location (never a Python literal);
- evidence files live INSIDE the repo and paths are recorded REPO-RELATIVE
  (no CWD dependence, no local-layout leaks);
- every read is parse-and-hash on the SAME bytes (no TOCTOU on citations);
- the frozen task list and the module pin are PENDING slots with policy —
  a run refusing while pending is the honest state (LI-PROBE-003).
"""

from __future__ import annotations

import json
import re
import tomllib
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError

MODULE_PENDING = "pending-reexport"
TASKS_PENDING = "pending-frozen-list"
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$")
_SHA_RE = re.compile(r"[0-9a-f]{64}")


def _read_bytes_labeled(repo_root: Path, rel: str, what: str) -> bytes:
    p = repo_root / rel
    try:
        raw = p.read_bytes()
    except FileNotFoundError as exc:
        raise SchemaError("LI-PROBE-003", f"{what} missing", {"path": rel}) from exc
    except OSError as exc:
        raise SchemaError("LI-PROBE-003", f"{what} unreadable", {"path": rel, "err": str(exc)}) from exc
    if not raw:
        raise SchemaError("LI-PROBE-003", f"{what} empty", {"path": rel})
    return raw


def _parse_toml(raw: bytes, what: str) -> dict:
    try:
        out = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-PROBE-003", f"{what} unparseable", {}) from exc
    if not isinstance(out, dict):
        raise SchemaError("LI-PROBE-003", f"{what} not a mapping", {})
    return out


def _evidence_entry(repo_root: Path, rel_path: str) -> dict:
    if not isinstance(rel_path, str) or not rel_path:
        raise SchemaError("LI-PROBE-003", "agent pin without evidence path", {})
    p = (repo_root / rel_path).resolve()
    try:
        p.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise SchemaError("LI-PROBE-003", "evidence path escapes the repo", {"path": rel_path}) from exc
    if not p.is_file():
        raise SchemaError("LI-PROBE-003", "evidence file missing", {"path": rel_path})
    return {"file": rel_path, "sha256": sha256(p.read_bytes()).hexdigest()}


def build_campaign_pins(repo_root: Path, *, observed_models: list[dict]) -> dict:
    """Assemble campaign-pins-v1. observed_models entries:
    {model, vendor_generation, evidence_file (repo-relative), verified_at (ISO)}."""
    root = Path(repo_root)
    d_raw = _read_bytes_labeled(root, "governance/act1-design/design.toml", "Act I design")
    t_raw = _read_bytes_labeled(root, "governance/act1-design/tasks.toml", "Act I tasks")
    dec_raw = _read_bytes_labeled(root, "governance/probe-design/decision.toml", "probe decision")
    design = _parse_toml(d_raw, "design.toml")
    tasks = _parse_toml(t_raw, "tasks.toml")
    _ = _parse_toml(dec_raw, "decision.toml")

    # the sealed floor: read from tasks.toml's [subset] — NOT a Python constant
    required = tasks.get("subset", {}).get("families_required")
    if not isinstance(required, int) or isinstance(required, bool) or required < 1:
        raise SchemaError("LI-PROBE-003", "tasks.toml [subset].families_required missing/invalid", {})

    scaffold = design.get("scaffold") or {}
    harness = {"name": scaffold.get("name"), "version_locked_by": scaffold.get("version_locked_by")}

    agents = []
    for m in observed_models:
        if not isinstance(m, dict):
            raise SchemaError("LI-PROBE-003", "agent entry not a mapping", {})
        model = m.get("model")
        gen = m.get("vendor_generation")
        if not isinstance(model, str) or not model.strip():
            raise SchemaError("LI-PROBE-003", "agent pin missing model", {})
        if not isinstance(gen, str) or not gen.strip():
            raise SchemaError("LI-PROBE-003", "agent pin missing vendor_generation", {"model": model})
        verified = m.get("verified_at")
        if not isinstance(verified, str) or not _ISO_DATE.match(verified):
            raise SchemaError("LI-PROBE-003", "agent pin needs verified_at (ISO)", {"model": model})
        agents.append({
            "model": model, "vendor_generation": gen,
            "evidence": _evidence_entry(root, m.get("evidence_file", "")),
            "verified_at": verified,
            "mismatch_policy": "re-collect the un-augmented arm alongside, disclose the drift in the paired publication",
        })
    families = {a["vendor_generation"] for a in agents} if agents else set()
    if len(families) < required:
        raise SchemaError("LI-PROBE-003", "fewer distinct families than FR-6 requires",
                          {"have": sorted(families), "required": required})

    frozen = root / "governance" / "act1-design" / "tasks-frozen.toml"
    task_set = (
        {"status": "frozen", "file": "governance/act1-design/tasks-frozen.toml",
         "sha256": sha256(frozen.read_bytes()).hexdigest(),
         "n": len(_parse_toml(frozen.read_bytes(), "tasks-frozen.toml").get("task", []))}
        if frozen.is_file() else
        {"status": TASKS_PENDING, "policy": "the frozen list generates at design freeze (tasks.toml[subset].selection_rule); pending is the record"}
    )
    payload = {
        "campaign": "act2-intervention",
        "task_set": task_set,
        "design": {"file": "governance/act1-design/design.toml", "sha256": sha256(d_raw).hexdigest()},
        "protocol": {"file": "governance/probe-design/decision.toml", "sha256": sha256(dec_raw).hexdigest()},
        "harness": harness,
        "agents": agents,
        "module": {"advisory_predictor_hash": MODULE_PENDING,
                   "posture": "sub-bar advisory baseline (branch iii) — measured, NOT certified",
                   "policy": "re-export via probe.arms.baseline_export before the window; runs refuse on pending"},
        "inputs": {  # AD-13: which corpus posture this campaign depends on
            "corpus_version": "corpus-v0",
            "clean_tier": "clean-tier/v0",
        },
    }
    return payload


def require_module_pin(payload: dict) -> str:
    """A run manifest cannot mint on a pending or malformed module pin."""
    h = (payload.get("module") or {}).get("advisory_predictor_hash")
    if not isinstance(h, str) or h == MODULE_PENDING or not _SHA_RE.fullmatch(h):
        raise SchemaError("LI-PROBE-003", "module pin pending or malformed", {"got": h})
    return h


def require_task_set(payload: dict) -> dict:
    ts = payload.get("task_set") or {}
    if ts.get("status") != "frozen" or not isinstance(ts.get("n"), int) or ts["n"] < 1:
        raise SchemaError("LI-PROBE-003", "task set not frozen", {"status": ts.get("status")})
    return ts


def write_campaign_pins(payload: dict, out_path: Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(out_path)
