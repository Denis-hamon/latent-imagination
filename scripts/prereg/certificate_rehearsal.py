"""Certificate rehearsal drill (story 7.1, AC4) — the full revocation /
supersession path exercised OFFLINE against fixtures in a TEMP store root.

This rehearsal issues NOTHING real: no live anchor, no real ledger, no real
certificate (the first real issuance is the Story 7.5 ceremony, gated on a
verdict that crossed the bar). It proves the machinery:

  1. certificates assemble and pass byte-level verification
     (verdict / sealed package / decision.toml cited by content hash)
  2. the store write contract accepts them under prereg ownership
  3. the anchor mechanics run on the disclosed offline-simulated lane
  4. ledger rows append in order: issued -> superseding (AD-3, never edited)
  5. THE DRILL — four states, each asserted against the gate seam:
       A issued (0.93 > bar)      ─┐
       B supersedes A     (0.85 ≤) ├─ downgrade: pin A => hard-fail (superseded)
                                    └─ pin B => hard-fail (at/below bar)
       C supersedes B  (0.95 > bar) ── re-probe crosses: pin C => AUTHORIZED
       D supersedes C     (0.84 ≤) ── late drift: pin D => hard-fail (at/below)
  6. every refusal is logged as a blocking_refused decision (never silent)
  7. the committed ceremony templates are hash-recorded (7.5 must cite the
     identical bytes)

Run:  uv run python scripts/prereg/certificate_rehearsal.py \
          --store-root <fresh-tmp-dir> --report <report.json>
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

from prereg.certificate import (
    assemble_certificate,
    currently_valid,
    verify_certificate_bytes,
)
from prereg.ledger import append_entry, certificate_entry
from store.emit import write_artifact

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "adapters" / "ots-anchor" / "src"))

from gate.blocking import authorize_blocking, refuse_blocking
from gate.decision_log import append_decision
from ots_anchor.anchor import (
    anchor_offline_simulated,
)

REHEARSAL_FINGERPRINT = "d0" * 32  # fixture key material — real key is provisioned at 7.5


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha(b: bytes) -> str:
    return sha256(b).hexdigest()


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store-root", required=True, type=Path,
                    help="FRESH temp store root (refused if non-empty — append-only discipline)")
    ap.add_argument("--report", required=True, type=Path)
    args = ap.parse_args(argv)

    store_root: Path = args.store_root
    if store_root.exists() and any(store_root.iterdir()):
        raise SystemExit(f"store-root {store_root} is non-empty — cut a fresh dir (append-only)")

    # ---- fixture + real governance inputs ---------------------------------
    verdict_bytes = (
        "# REHEARSAL FIXTURE verdict (NOT a real probe verdict)\n"
        "Matched precision 0.93 against registered bar 0.8889 — fictional\n"
        "above-bar result used ONLY to exercise the FR-21 machinery.\n"
    ).encode()
    (store_root / "fixtures").mkdir(parents=True)
    (store_root / "fixtures" / "verdict-rehearsal.md").write_bytes(verdict_bytes)

    package_bytes = (REPO / "governance/probe-design/package-manifest.json").read_bytes()
    decision_bytes = (REPO / "governance/probe-design/decision.toml").read_bytes()
    decision = tomllib.loads(decision_bytes.decode())
    bar_toml = decision["bar"]
    bar = {
        "formula": bar_toml["net_positive_precision_formula"],
        "cost_exec_usd": float(bar_toml["cost_exec_usd"]),
        "cost_regen_usd": float(bar_toml["cost_regen_usd"]),
        "registered_bar": float(bar_toml["registered_bar"]),
    }
    code_commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    citations = {
        "verdict_citation": {"artifact": str(store_root / "fixtures/verdict-rehearsal.md"),
                             "sha256": _sha(verdict_bytes)},
        "package_citation": {"artifact": "governance/probe-design/package-manifest.json",
                             "sha256": _sha(package_bytes)},
        "decision_citation": {"artifact": "governance/probe-design/decision.toml",
                              "sha256": _sha(decision_bytes)},
    }
    signer = {"identity": "builder (REHEARSAL — not a real issuance)",
              "key_fingerprint": REHEARSAL_FINGERPRINT}

    def _make(precision, wilson, *, direction="issued", supersedes=None, reason=None):
        cert = assemble_certificate(
            direction=direction, generations=("rehearsal-gen-1",),
            certified_precision=precision, precision_wilson95=wilson,
            bar=dict(bar), signer=dict(signer),
            supersedes=supersedes, supersession_reason=reason, **citations)
        body = cert.to_dict() | {"certificate_hash": cert.certificate_hash}
        rep = verify_certificate_bytes(
            body, verdict_bytes=verdict_bytes,
            package_manifest_bytes=package_bytes, decision_bytes=decision_bytes)
        if not rep.ok:
            raise SystemExit(f"byte verification failed for {precision}: {rep.errors}")
        return cert, body

    a, a_body = _make(0.93, (0.88, 0.96))
    b, b_body = _make(0.85, (0.79, 0.90), direction="superseding", supersedes=a.certificate_hash,
                      reason="rehearsal re-measurement dropped certified precision to "
                             "0.85 <= bar 0.8889 (downgrade)")
    c, c_body = _make(0.95, (0.91, 0.98), direction="superseding", supersedes=b.certificate_hash,
                      reason="rehearsal re-probe crossed the bar again (0.95 > 0.8889)")
    d, d_body = _make(0.84, (0.78, 0.89), direction="superseding", supersedes=c.certificate_hash,
                      reason="rehearsal late drift: re-measurement fell to 0.84 <= bar (downgrade)")

    # ---- store artifacts + disclosed offline anchor + ledger --------------
    ledger = store_root / "prereg-ledger.jsonl"
    proofs = store_root / "proofs"
    proofs.mkdir(parents=True, exist_ok=True)
    anchor_modes: list[str] = []

    def _store(cert, body, slug):
        f = store_root / "fixtures" / f"{slug}.json"
        f.write_text(json.dumps(body, sort_keys=True) + "\n")
        art = write_artifact(
            "prereg", "threshold-certificate", slug, "v1", [f],
            {"verdict_hash": citations["verdict_citation"]["sha256"],
             "package_hash": citations["package_citation"]["sha256"],
             "decision_hash": citations["decision_citation"]["sha256"],
             "code_commit": code_commit},
            store_root)
        proof_path = proofs / f"{cert.certificate_hash[:16]}.sim.ots"
        proof_path.write_bytes(b"REHEARSAL SIMULATED PROOF - no external anchor (story 7.1)\n")
        rec = anchor_offline_simulated(cert.certificate_hash, str(proof_path))
        row = certificate_entry(
            cert.certificate_hash, cert.direction,
            citations["verdict_citation"]["sha256"], list(cert.generations),
            cert.certified_precision, cert.bar.registered_bar,
            _now(), rec.anchored_at,
            anchor_mode="ots-simulated (rehearsal, story 7.1 — no live anchor)",
            proof_ref=str(proof_path),
            purpose="7.1 revocation drill fixture",
            supersedes=cert.supersedes, supersession_reason=cert.supersession_reason)
        append_entry(ledger, row)
        anchor_modes.append(row["anchor_mode"])
        return art

    arts = {slug: _store(cert, body, slug)
            for slug, (cert, body) in
            [("rehearsal-cert-a", (a, a_body)), ("rehearsal-cert-b", (b, b_body)),
             ("rehearsal-cert-c", (c, c_body)), ("rehearsal-cert-d", (d, d_body))]}

    # ---- the drill: gate hard-fails / authorizes exactly as FR-21 demands --
    manifests = {
        "downgrade": {"certificates": {a.certificate_hash: a_body, b.certificate_hash: b_body}},
        "upgrade": {"certificates": {a.certificate_hash: a_body, b.certificate_hash: b_body,
                                     c.certificate_hash: c_body}},
        "late-drift": {"certificates": {h: bd for h, bd in
                                        [(a.certificate_hash, a_body), (b.certificate_hash, b_body),
                                         (c.certificate_hash, c_body), (d.certificate_hash, d_body)]}},
    }
    deployer_dir = store_root.parent / f"{store_root.name}-deployer"
    decisions = deployer_dir / "decisions.jsonl"
    drill: dict[str, object] = {}

    def _handoff(name, manifest, cert, *, expect):
        snap = store_root / f"handoff-{name}"
        snap.mkdir(parents=True)
        (snap / "certificate.json").write_text(json.dumps(cert[1], sort_keys=True))
        (snap / "supersession-manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        pin = cert[0].certificate_hash
        try:
            auth = authorize_blocking(snap, expected_certificate_hash=pin,
                                      query_generation="rehearsal-gen-1")
        except Exception as exc:  # SchemaError (LI-GATE-006) expected on deny paths
            code = getattr(exc, "code", None)
            if expect == "deny" and code == "LI-GATE-006":
                append_decision(decisions, refuse_blocking(str(exc), certificate_hint=pin))
                drill[name] = {"result": "hard-fail", "code": code, "reason": str(exc)[:160]}
                return
            raise
        if expect != "allow":
            raise SystemExit(f"drill {name}: expected hard-fail, got authorization {auth}")
        drill[name] = {"result": "authorized", "certificate_hash": auth.certificate_hash,
                       "certified_precision": auth.certified_precision}

    _handoff("1-superseeded", manifests["downgrade"], (a, a_body), expect="deny")
    _handoff("2-below-bar", manifests["downgrade"], (b, b_body), expect="deny")
    _handoff("3-reprobe-crossed", manifests["upgrade"], (c, c_body), expect="allow")
    _handoff("4-late-drift", manifests["late-drift"], (d, d_body), expect="deny")

    assert drill["1-superseeded"]["result"] == "hard-fail"
    assert "superseded" in drill["1-superseeded"]["reason"]
    assert drill["2-below-bar"]["result"] == "hard-fail"
    assert "at/below" in drill["2-below-bar"]["reason"]
    assert drill["3-reprobe-crossed"]["result"] == "authorized"
    assert drill["4-late-drift"]["result"] == "hard-fail"
    assert "at/below" in drill["4-late-drift"]["reason"]
    assert not currently_valid(manifests["late-drift"]["certificates"], a.certificate_hash)
    assert not currently_valid(manifests["late-drift"]["certificates"], b.certificate_hash)
    assert not currently_valid(manifests["late-drift"]["certificates"], c.certificate_hash)
    assert currently_valid(manifests["late-drift"]["certificates"], d.certificate_hash)

    # ---- committed template hashes (7.5 must cite identical bytes) --------
    templates = {}
    for name in ("issued.md", "superseding.md"):
        raw = (REPO / "governance" / "certificates" / "templates" / name).read_bytes()
        templates[name] = _sha(raw)

    report = {
        "rehearsal": "7.1-revocation-drill",
        "generated_at": _now(),
        "doctrine": "REHEARSAL ONLY — no real certificate issued; live issuance is the 7.5 "
                    "ceremony, gated on a verdict that crossed the registered bar",
        "store_root": str(store_root),
        "code_commit": code_commit,
        "fixtures": {"verdict_sha256": _sha(verdict_bytes),
                     "package_manifest_sha256": _sha(package_bytes),
                     "decision_toml_sha256": _sha(decision_bytes)},
        "bar": bar,
        "certificates": {slug: {"certificate_hash": cert.certificate_hash,
                                "direction": cert.direction,
                                "certified_precision": cert.certified_precision,
                                "artifact_manifest": str(arts[slug].manifest_path)}
                         for slug, (cert, _) in
                         [("rehearsal-cert-a", (a, a_body)), ("rehearsal-cert-b", (b, b_body)),
                          ("rehearsal-cert-c", (c, c_body)), ("rehearsal-cert-d", (d, d_body))]},
        "anchor_mode": sorted(set(anchor_modes)),
        "ledger_rows": [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()],
        "drill": drill,
        "refusals_logged": len(decisions.read_text().splitlines()),
        "templates": templates,
        "outcome": "PASS",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"outcome": "PASS", "report": str(args.report),
                      "anchor_mode": report["anchor_mode"]}, indent=2))
    return report


if __name__ == "__main__":
    main()
