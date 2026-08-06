"""Act II publication assembly (story 6.4): the intervention packet, chained
to the Act I release, branch-explicit, SM-3 recorded.

Reuses the Epic-2 machinery end-to-end: the release packet goes through the
SAME ceremony (scripts/prereg/release_ceremony.py --packet) — chain topology
prereg.assemble_chain, anchor via the ots adapter, WORM write on the node.
Zenodo DOI = adapter pending (2.6.4) — this file says so in the manifest, no
theater. The branch's preprint template is selected MECHANICALLY from the
sealed OQ-4 verdict (both templates were anchored in advance, 6.2).
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError

SHA_RE_LEN = 64


def _need_json(p: Path, what: str) -> dict:
    try:
        raw = Path(p).read_bytes()
        obj = json.loads(raw)
    except FileNotFoundError as exc:
        raise SchemaError("LI-PUB-030", f"act2 release input missing: {what}", {"path": str(p)}) from exc
    except ValueError as exc:
        raise SchemaError("LI-PUB-030", f"act2 release input unparseable: {what}", {"path": str(p)}) from exc
    if not isinstance(obj, dict):
        raise SchemaError("LI-PUB-030", f"act2 release input not a mapping: {what}", {})
    return obj


def _check_sha(value: str, what: str) -> str:
    if not isinstance(value, str) or len(value) != SHA_RE_LEN or any(c not in "0123456789abcdef" for c in value):
        raise SchemaError("LI-PUB-030", f"{what} must be 64-hex", {"got": str(value)[:40]})
    return value


def select_preprint_template(delta_verdict_met: bool) -> str:
    """Branch mechanics: met → material-reduction.md; else below-threshold.md.
    Both pre-anchored (governance/act2/verdict-templates/). Never ad hoc."""
    return "material-reduction.md" if delta_verdict_met else "below-threshold.md"


def sm3_evaluation(delta_report: dict, rerun_report: dict) -> dict:
    """SM-3's target recorded against THIS release:
    third-party-reproducible False-Start delta ≥ pre-registered publishable
    minimum, after a declared-independent re-run within tolerance."""
    try:
        delta_pp = float(delta_report["published_delta_pp"]) if "published_delta_pp" in delta_report else None
        if delta_pp is None:
            delta_pp = float(delta_report["reproduced_delta_pp"])
        within = bool(rerun_report["within_tolerance"])
        minimum = float(delta_report.get("minimum_pp", 5.0))
    except (KeyError, TypeError, ValueError) as exc:
        raise SchemaError("LI-PUB-030", "SM-3 evaluation inputs malformed", {}) from exc
    met = bool(delta_pp >= minimum and within)
    return {
        "target": "SM-3: third-party-reproducible False-Start delta ≥ pre-registered publishable minimum (OQ-4), post declared-independent re-run",
        "measured": {"delta_pp": delta_pp, "within_tolerance": within, "publishable_minimum_pp": minimum},
        "outcome": "met" if met else "not met — recorded, published as such",
    }


def assemble_act2_release(
    packet_dir: Path,
    *,
    delta_json: Path,
    rerun_report_json: Path,
    verdict_text: str,
    campaign_pins_json: Path,
    act1_release_hash: str,
    code_commit: str,
) -> dict:
    """Assemble the Act II packet content + return the release manifest block.
    Requires the 6.3 gate already applied (rerun report PRESENT before call —
    double-guarded here: a publication never proceeds without it)."""
    if not isinstance(verdict_text, str) or "{" in verdict_text:  # leftover placeholders refuse
        raise SchemaError("LI-PUB-030", "verdict text unrendered (literal placeholders)", {})
    act1 = _check_sha(act1_release_hash, "act1_release_hash")
    delta = _need_json(delta_json, "delta figure")
    rerun = _need_json(rerun_report_json, "rerun report")
    _need_json(campaign_pins_json, "campaign pins")  # structural validation; bytes ship as-is
    if (delta.get("oq4") or {}).get("met") is None:
        raise SchemaError("LI-PUB-030", "delta figure lacks the OQ-4 verdict", {})

    packet_dir = Path(packet_dir)
    packet_dir.mkdir(parents=True, exist_ok=True)
    for src, name in ((delta_json, "delta.json"), (rerun_report_json, "rerun-report.json"),
                      (campaign_pins_json, "campaign-pins.json")):
        (packet_dir / name).write_bytes(Path(src).read_bytes())
    (packet_dir / "verdict.md").write_text(verdict_text + "\n", encoding="utf-8")

    sm3 = sm3_evaluation(
        {**{k: delta.get("claim_line", {}).get(k) for k in ("erbve_delta_pp",)},
         "published_delta_pp": delta.get("claim_line", {}).get("erbve_delta_pp"),
         "minimum_pp": delta.get("oq4", {}).get("minimum_publishable_pp")},
        rerun,
    )
    manifest_block = {
        "act": 2,
        "references_act1_release": act1,
        "preprint_branch": {
            "verdict": delta["oq4"]["verdict"],
            "template": select_preprint_template(bool(delta["oq4"]["met"])),
        },
        "sm3": sm3,
        "contents": {
            "delta_json_sha256": sha256(Path(delta_json).read_bytes()).hexdigest(),
            "rerun_report_sha256": sha256(Path(rerun_report_json).read_bytes()).hexdigest(),
            "campaign_pins_sha256": sha256(Path(campaign_pins_json).read_bytes()).hexdigest(),
            "verdict_template": select_preprint_template(bool(delta["oq4"]["met"])),
        },
        "distribution_note": "Zenodo DOI adapter pending (story 2.6 task 4) — recorded, not faked; WORM + GitHub via the standard ceremony",
        "code_commit": code_commit,
    }
    (packet_dir / "release-manifest-block.json").write_text(
        json.dumps(manifest_block, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_block
