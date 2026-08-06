"""Act II publication assembly (story 6.4 + CR): the intervention packet,
chained to the Act I release by VALUE-binding, branch-explicit, SM-3 recorded
on the THIRD-PARTY number.

Posture corrections from the review:
- SM-3 is evaluated on the REPRODUCED delta (the rerun report), published is
  recorded alongside — never the first-party number alone;
- the rerun report must ANCHOR this exact delta figure
  (bitwise_anchor.expected_sha256 == sha256(delta bytes));
- verdict.md is RENDERED HERE from the anchored templates (no caller text);
- assembly validates everything FIRST, refuses to overwrite a non-empty
  packet (atomic-claim, house pattern);
- the distribution note records INTENT, never executed effects.
"""

from __future__ import annotations

import json
import math
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from core_schema.errors import SchemaError

_HEX64 = re.compile(r"[0-9a-f]{64}")
_LEFTOVER = re.compile(r"\{[a-z_]+\}")


def _read_once(p: Path, what: str) -> bytes:
    try:
        return Path(p).read_bytes()
    except OSError as exc:
        raise SchemaError("LI-PUB-030", f"act2 release input unreadable: {what}",
                          {"path": str(p), "err": type(exc).__name__}) from exc


def _need_json_bytes(raw: bytes, what: str) -> dict:
    try:
        obj = json.loads(raw)
    except ValueError as exc:
        raise SchemaError("LI-PUB-030", f"act2 release input unparseable: {what}", {}) from exc
    if not isinstance(obj, dict):
        raise SchemaError("LI-PUB-030", f"act2 release input not a mapping: {what}", {})
    return obj


def select_preprint_template(delta_verdict_met: bool) -> str:
    """Branch mechanics: met → material-reduction.md; else below-threshold.md."""
    return "material-reduction.md" if delta_verdict_met else "below-threshold.md"


def _check_sha(value: str, what: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise SchemaError("LI-PUB-030", f"{what} must be 64-hex lowercase", {"got": str(value)[:40]})
    return value


def _finite(v: Any = None) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SchemaError("LI-PUB-030", "sealed numeric malformed", {"got": str(v)[:30]})
    f = float(v)
    if not math.isfinite(f):
        raise SchemaError("LI-PUB-030", "non-finite number in inputs", {})
    return f


def _strict_bool(v: Any, what: str) -> bool:
    if v is True:
        return True
    if v is False:
        return False
    raise SchemaError("LI-PUB-030", f"{what} must be a JSON boolean", {"got": repr(v)[:40]})


def sm3_evaluation(rerun_report: dict, *, minimum_pp: float) -> dict:
    """SM-3 against THIS release — on the THIRD-PARTY (reproduced) number.

    met ⇔ reproduced delta ≥ sealed publishable minimum AND the rerun was
    within tolerance AND the anchor matched the published figure."""
    reproduced = _finite(rerun_report.get("reproduced_delta_pp"))
    published = _finite(rerun_report.get("published_delta_pp"))
    within = _strict_bool(rerun_report.get("within_tolerance"), "within_tolerance")
    anchor = rerun_report.get("bitwise_anchor") or {}
    anchor_ok = _strict_bool(anchor.get("bitwise_equal"), "bitwise_anchor.bitwise_equal")
    minimum = _finite(minimum_pp)
    met = bool(reproduced >= minimum and within and anchor_ok)
    return {
        "target": "SM-3: third-party-reproducible False-Start delta ≥ pre-registered minimum (OQ-4), post declared-independent re-run within sealed tolerance + byte-anchored",
        "measured": {"reproduced_delta_pp": reproduced, "published_delta_pp": published,
                     "within_tolerance": within, "anchor_byte_identical": anchor_ok,
                     "publishable_minimum_pp": minimum},
        "outcome": "met" if met else "not met — recorded, published as such",
    }


def _render_verdict(delta: dict, templates_dir: Path) -> tuple[str, str]:
    """Render HERE through the house renderer — the packet's text can never
    drift from the template the manifest names."""
    from harness.delta import render_verdict

    met = _strict_bool((delta.get("oq4") or {}).get("met"), "oq4.met")
    verdict_label = (delta.get("oq4") or {}).get("verdict")
    if verdict_label not in ("material-reduction", "below-threshold"):
        raise SchemaError("LI-PUB-030", "oq4.verdict malformed", {"got": verdict_label})
    if (verdict_label == "material-reduction") != met:
        raise SchemaError("LI-PUB-030", "oq4.verdict contradicts oq4.met",
                          {"verdict": verdict_label, "met": met})
    text = render_verdict(delta, templates_dir)
    if _LEFTOVER.search(text):
        raise SchemaError("LI-PUB-030", "verdict render left literal placeholders", {})
    return select_preprint_template(met), text


def assemble_act2_release(
    packet_dir: Path,
    *,
    delta_json: Path,
    rerun_report_json: Path,
    templates_dir: Path,
    campaign_pins_json: Path,
    act1_release_hash: str,
    code_commit: str,
) -> dict:
    """Assemble the Act II packet; returns the manifest block. ALL validation
    precedes ANY write; a non-empty packet dir refuses (cut a new version)."""
    packet_dir = Path(packet_dir)
    if packet_dir.exists() and any(packet_dir.iterdir()):
        raise SchemaError("LI-PUB-030", "packet dir non-empty — cut a new version "
                          "(append-only discipline)", {"path": str(packet_dir)})

    delta_raw = _read_once(delta_json, "delta figure")
    rerun_raw = _read_once(rerun_report_json, "rerun report")
    pins_raw = _read_once(campaign_pins_json, "campaign pins")
    delta = _need_json_bytes(delta_raw, "delta figure")
    rerun = _need_json_bytes(rerun_raw, "rerun report")
    _need_json_bytes(pins_raw, "campaign pins")
    act1 = _check_sha(act1_release_hash, "act1_release_hash")
    code_commit_c = _check_sha(code_commit, "code_commit")

    if not isinstance((delta.get("claim_line")), dict) or "erbve_delta_pp" not in delta["claim_line"]:
        raise SchemaError("LI-PUB-030", "delta figure lacks claim_line.erbve_delta_pp", {})
    _finite(delta["claim_line"]["erbve_delta_pp"])
    template_name, verdict_text = _render_verdict(delta, templates_dir)

    # CROSS-BINDING: the rerun report must anchor THIS delta figure's bytes
    anchor = rerun.get("bitwise_anchor") or {}
    expected = anchor.get("expected_sha256")
    if not isinstance(expected, str) or not _HEX64.fullmatch(expected):
        raise SchemaError("LI-PUB-030", "rerun report lacks a byte anchor", {})
    if expected != sha256(delta_raw).hexdigest():
        raise SchemaError(
            "LI-PUB-030", "rerun report anchors a DIFFERENT delta figure — chain broken",
            {"rerun_expected": expected[:12], "delta_figure": sha256(delta_raw).hexdigest()[:12]},
        )
    minimum_pp = _finite((delta.get("oq4") or {}).get("minimum_publishable_pp"))
    sm3 = sm3_evaluation(
        {**rerun, "published_delta_pp": delta["claim_line"]["erbve_delta_pp"]},
        minimum_pp=minimum_pp,
    )
    template_bytes = _read_once(Path(templates_dir) / template_name, "preprint template")

    manifest_block = {
        "act": 2,
        "references_act1_release_hash": act1,
        "preprint_branch": {"verdict": delta["oq4"]["verdict"], "template": template_name,
                             "template_sha256": sha256(template_bytes).hexdigest()},
        "sm3": sm3,
        "contents": {
            "delta_json_sha256": sha256(delta_raw).hexdigest(),
            "rerun_report_sha256": sha256(rerun_raw).hexdigest(),
            "campaign_pins_sha256": sha256(pins_raw).hexdigest(),
            "verdict_md_sha256": None,  # filled below after the write
        },
        "distribution_note": ("INTENT: this packet ships via the standard ceremony "
                              "(chain via prereg.assemble_chain, OTS anchor, WORM write at the node "
                              "window). Zenodo DOI adapter pending (story 2.6 task 4), recorded not faked. "
                              "Nothing in this block asserts execution."),
        "code_commit": code_commit_c,
    }
    try:
        packet_dir.mkdir(parents=True, exist_ok=True)
        for raw, name in ((delta_raw, "delta.json"), (rerun_raw, "rerun-report.json"),
                          (pins_raw, "campaign-pins.json")):
            (packet_dir / name).write_bytes(raw)
        (packet_dir / "verdict.md").write_bytes((verdict_text + "\n").encode("utf-8"))
        manifest_block["contents"]["verdict_md_sha256"] = sha256(
            (packet_dir / "verdict.md").read_bytes()).hexdigest()
        (packet_dir / "release-manifest-block.json").write_text(
            json.dumps(manifest_block, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise SchemaError("LI-PUB-030", "packet write failed",
                          {"err": type(exc).__name__}) from exc
    return manifest_block
