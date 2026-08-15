"""First certificate ceremony (story 7.5, FR-21) — the issuance machinery +
field validation, exercised OFFLINE on fixtures.

The LIVE ceremony (real OTS anchor, WORM bucket, Zenodo DOI, HF mirror, real
verdict hash citing a crossing-bar probe verdict) is GATED by doctrine — no
arm crossed 0.8889 (branch iii). This script proves the ceremony machinery:
composes 7.1 (certificate) + 7.2 (workload check) + 7.3 (decision path +
budget) + 7.4 (shadow sampling) into a release packet via the 2.6 release
machinery, runs field validation, and writes a ceremony report. The live
ceremony runs when a next-cycle verdict crosses the bar.

Run:  uv run python scripts/prereg/certificate_ceremony.py \
          --store-root <fresh-tmp> --report <report.json>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "adapters" / "ots-anchor" / "src"))

from gate.blocking import (
    BlockContext,
    LocalCheckState,
    authorize_blocking,
    evaluate_blocking,
    load_false_block_budget,
)
from gate.shadow import select_for_shadow
from gate.testing import (
    write_certificate_snapshot,
)
from prereg.certificate import (
    BAR_FORMULA,
    assemble_certificate,
    verify_certificate_bytes,
)
from prereg.ledger import append_entry, certificate_entry
from store.emit import write_artifact

sys.path.insert(0, str(REPO / "scripts" / "prereg"))
from release_ceremony import anchor_chain, build_release_artifacts

BUDGET_PATH = REPO / "governance" / "gate" / "false-block-budget-v1.toml"
TEMPLATE_PATH = REPO / "governance" / "certificates" / "templates" / "issued.md"
REHEARSAL_PATH = REPO / "scripts" / "prereg" / "certificate_rehearsal.py"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha(b: bytes) -> str:
    return sha256(b).hexdigest()


def _render_ceremony_page(cert, verdict_sha: str, budget_seal: str) -> str:
    """Fill the issued.md template with fixture values; assert no residual placeholders."""
    tpl = TEMPLATE_PATH.read_text()
    replacements = {
        "{certificate_hash}": cert.certificate_hash,
        "{generations}": ", ".join(cert.generations),
        "{certified_precision}": f"{cert.certified_precision:.4f}",
        "{wilson_lo}": f"{cert.precision_wilson95[0]:.4f}",
        "{wilson_hi}": f"{cert.precision_wilson95[1]:.4f}",
        "{registered_bar}": f"{cert.bar.registered_bar:.4f}",
        "{bar_formula}": cert.bar.formula,
        "{cost_exec_usd}": f"{cert.bar.cost_exec_usd}",
        "{cost_regen_usd}": f"{cert.bar.cost_regen_usd}",
        "{verdict_artifact}": "governance/probe-design/runs/verdict-REHEARSAL.md (fixture)",
        "{verdict_sha256}": verdict_sha,
        "{package_sha256}": cert.package_citation.sha256,
        "{decision_sha256}": cert.decision_citation.sha256,
        "{code_commit}": subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip(),
        "{signer_identity}": cert.signer.identity,
        "{key_fingerprint}": cert.signer.key_fingerprint,
        "{anchor_mode}": "ots-simulated (ceremony rehearsal, story 7.5 — no live anchor)",
        "{proof_ref}": "proofs/ceremony-rehearsal.sim.ots",
        "{anchored_at}": _now(),
    }
    rendered = tpl
    for k, v in replacements.items():
        rendered = rendered.replace(k, v)
    # check for unreplaced {placeholders} (not prose mentions like `{placeholder}`)
    import re
    unfilled = re.findall(r"\{[a-z_]+\}", rendered)
    # filter out the prose mention `{placeholder}` which is a literal in the template header
    unfilled = [p for p in unfilled if p != "{placeholder}"]
    if unfilled:
        raise SystemExit(f"ceremony page has residual placeholders: {unfilled[:5]}")
    return rendered


def _field_validation(cert, cert_snapshot_root, budget, report_out: dict) -> dict:
    """AC2: blocking active ONLY under certificate + local-check conditions."""
    pin = cert.certificate_hash
    results = {}

    # BLOCK path: all legs green
    auth = authorize_blocking(cert_snapshot_root, expected_certificate_hash=pin,
                               query_generation="rehearsal-gen-1")
    local = LocalCheckState(precision=0.95, checked_at=_now(), blocking_enabled=True)
    ctx = BlockContext(certificate=auth, local_check=local, budget=budget,
                       max_age_days=14, binarization_threshold=0.5)
    decision = evaluate_blocking(flip_probability=0.9,
                                  prediction_target_tier="diff_touched",
                                  context=ctx, now=datetime.now(UTC))
    results["block_path"] = {"action": decision.action, "reason": decision.reason[:120]}
    assert decision.action == "block", f"block path failed: {decision.reason}"

    # Shadow sampling: the block decision is deterministically sampled
    shadowed = select_for_shadow("e" * 64, pin, shadow_rate=0.10)
    results["shadow_sampled"] = shadowed

    # ADVISE paths: break each leg
    for leg_name, break_fn in [
        ("no_budget", lambda: BlockContext(certificate=auth, local_check=local,
                                            budget=None, max_age_days=14,
                                            binarization_threshold=0.5)),
        ("local_below_bar", lambda: BlockContext(certificate=auth,
            local_check=LocalCheckState(0.5, _now(), True), budget=budget,
            max_age_days=14, binarization_threshold=0.5)),
        ("stale_check", lambda: BlockContext(certificate=auth,
            local_check=LocalCheckState(0.95, "2026-07-01T00:00:00Z", True),
            budget=budget, max_age_days=14, binarization_threshold=0.5)),
        ("no_denominator", lambda: (auth, None)),
        ("no_flip", lambda: (auth, "diff_touched")),
    ]:
        if leg_name in ("no_denominator", "no_flip"):
            a, tier = break_fn()
            ctx2 = BlockContext(certificate=a, local_check=local, budget=budget,
                                max_age_days=14, binarization_threshold=0.5)
            prob = 0.3 if leg_name == "no_flip" else 0.9
            d = evaluate_blocking(flip_probability=prob,
                                  prediction_target_tier=tier,
                                  context=ctx2, now=datetime.now(UTC))
        else:
            ctx2 = break_fn()
            d = evaluate_blocking(flip_probability=0.9,
                                  prediction_target_tier="diff_touched",
                                  context=ctx2, now=datetime.now(UTC))
        results[leg_name] = {"action": d.action, "reason": d.reason[:80]}
        assert d.action == "advise", f"{leg_name} should advise, got {d.action}"

    report_out["field_validation"] = results
    return results


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description="first certificate ceremony (story 7.5)")
    ap.add_argument("--store-root", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    args = ap.parse_args(argv)

    store_root: Path = args.store_root
    if store_root.exists() and any(store_root.iterdir()):
        raise SystemExit(f"store-root {store_root} is non-empty — cut a fresh dir (append-only)")
    store_root.mkdir(parents=True, exist_ok=True)

    # --- fixture governance inputs ---
    verdict_bytes = (
        "# REHEARSAL FIXTURE verdict (NOT a real probe verdict)\n"
        "Matched precision 0.93 above bar 0.8889 — fictional above-bar result.\n"
    ).encode()
    (store_root / "fixtures").mkdir(parents=True)
    (store_root / "fixtures" / "verdict-rehearsal.md").write_bytes(verdict_bytes)
    package_bytes = (REPO / "governance/probe-design/package-manifest.json").read_bytes()
    decision_bytes = (REPO / "governance/probe-design/decision.toml").read_bytes()
    decision = tomllib.loads(decision_bytes.decode())
    bar_toml = decision["bar"]

    code_commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()

    cert = assemble_certificate(
        direction="issued",
        verdict_citation={"artifact": "governance/probe-design/runs/verdict-rehearsal.md",
                          "sha256": _sha(verdict_bytes)},
        package_citation={"artifact": "governance/probe-design/package-manifest.json",
                         "sha256": _sha(package_bytes)},
        decision_citation={"artifact": "governance/probe-design/decision.toml",
                         "sha256": _sha(decision_bytes)},
        generations=("rehearsal-gen-1",),
        certified_precision=0.93,
        precision_wilson95=(0.88, 0.96),
        bar={"formula": BAR_FORMULA,
             "cost_exec_usd": float(bar_toml["cost_exec_usd"]),
             "cost_regen_usd": float(bar_toml["cost_regen_usd"]),
             "registered_bar": float(bar_toml["registered_bar"])},
        signer={"identity": "builder (REHEARSAL — not a real issuance)",
                "key_fingerprint": "d0" * 32},
    )
    cert_body = cert.to_dict() | {"certificate_hash": cert.certificate_hash}
    rep = verify_certificate_bytes(
        cert_body,
        verdict_bytes=verdict_bytes,
        package_manifest_bytes=package_bytes,
        decision_bytes=decision_bytes)
    if not rep.ok:
        raise SystemExit(f"byte verification failed: {rep.errors}")

    # --- store artifact ---
    cert_file = store_root / "fixtures" / "certificate.json"
    cert_file.write_text(json.dumps(cert_body, sort_keys=True) + "\n")
    write_artifact("prereg", "threshold-certificate", "ceremony-cert", "v1",
                   [cert_file],
                   {"verdict_hash": _sha(verdict_bytes),
                    "package_hash": _sha(package_bytes),
                    "decision_hash": _sha(decision_bytes),
                    "code_commit": code_commit},
                   store_root)

    # --- release packet via 2.6 machinery ---
    ceremony_page = _render_ceremony_page(
        cert, _sha(verdict_bytes),
        load_false_block_budget(BUDGET_PATH).seal_sha256)
    packet_dir = store_root / "ceremony-packet"
    packet_dir.mkdir(parents=True)
    (packet_dir / "certificate.json").write_text(json.dumps(cert_body, sort_keys=True))
    (packet_dir / "ceremony-page.md").write_text(ceremony_page)
    arts = build_release_artifacts(REPO, store_root, packet=packet_dir,
                                    release_id="certificate-ceremony-rehearsal-2026-08-15")
    anchor_payload = anchor_chain(REPO, arts, store_root)

    # --- ledger row ---
    append_entry(store_root / "prereg-ledger.jsonl", certificate_entry(
        cert.certificate_hash, "issued", _sha(verdict_bytes),
        list(cert.generations), cert.certified_precision, cert.bar.registered_bar,
        _now(), anchor_payload["record"]["anchored_at"],
        anchor_mode=anchor_payload["anchor_mode"],
        proof_ref=anchor_payload["record"]["ots_proof_ref"],
        purpose="7.5 ceremony rehearsal — fixture issuance (no live anchor)",
    ))

    # --- pinned hand-off for field validation ---
    cert_snap = store_root / "cert-snapshot"
    write_certificate_snapshot(cert_snap, [cert], cert)

    # --- field validation (AC2) ---
    budget = load_false_block_budget(BUDGET_PATH)
    report: dict = {}
    _field_validation(cert, cert_snap, budget, report)

    # --- 7.1 revocation-drill artifact links (AC3) ---
    report["revocation_drill_link"] = {
        "rehearsal_script": str(REHEARSAL_PATH.relative_to(REPO)),
        "template_issued_sha256": _sha(TEMPLATE_PATH.read_bytes()),
        "template_superseding_sha256": _sha(
            (REPO / "governance/certificates/templates/superseding.md").read_bytes()),
    }

    report.update({
        "ceremony": "7.5-first-certificate-rehearsal",
        "doctrine": "REHEARSAL ONLY — no real certificate issued; live ceremony "
                    "gated on a verdict that crosses the bar",
        "store_root": str(store_root),
        "certificate": {"hash": cert.certificate_hash, "precision": cert.certified_precision,
                         "generations": list(cert.generations)},
        "release": {"release_id": arts["release_id"],
                     "release_hash": arts["release_hash"],
                     "anchor_mode": anchor_payload["anchor_mode"],
                     "chain_hash": anchor_payload["chain"]["chain_hash"]},
        "ceremony_page_template_sha256": _sha(TEMPLATE_PATH.read_bytes()),
        "outcome": "PASS",
    })
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"outcome": "PASS", "report": str(args.report)}, indent=2))
    return report


if __name__ == "__main__":
    main()
