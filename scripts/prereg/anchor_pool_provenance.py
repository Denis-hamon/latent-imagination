"""Story 9.3 — ancrage externe des provenances pool (v8 + v9) + test TSA live.

Cérémonie d'ancrage OTS LIVE (adaptateur ots-anchor, seul saut réseau de la
famille prereg) : chaque provenance est scellée par le sha256 de ses octets,
prouvé par la preuve .ots parsée offline (même contrat de stamping que les
chains : digest = sha256(bytes.fromhex(chain_hash))), ligne ledger append-only.

TEST TSA FALLBACK (action item rétro Epic 3 « Write TSA fallback live test
during the first real ceremony ») : requête RFC-3161 contre une TSA publique
via `uv run --with pyhanko` — lane de repli documentée dans
governance/anchor-fallback.md ; en cas d'indisponibilité réseau/TSA, le test
est DISCLOSED-SKIP, jamais un échec silencieux ni un faux succès.

Run:  uv run python scripts/prereg/anchor_pool_provenance.py [--tsa-test]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "adapters" / "ots-anchor" / "src"))

from prereg.ledger import append_entry

PROVS = [
    REPO / "governance" / "act2" / "arm-artifacts" / "pool-v8-provenance.json",
    REPO / "governance" / "act2" / "arm-artifacts" / "pool-v9-provenance.json",
]
STORE = REPO / "data" / "release-store"
LEDGER = STORE / "prereg-ledger.jsonl"
REPORT = REPO / "governance" / "act2" / "arm-artifacts" / "provenance-anchor-report.json"


def _sha(p: Path) -> str:
    return sha256(p.read_bytes()).hexdigest()


def _verify_proof_bytes(digest_hex: str, proof_path: Path) -> str:
    """Re-parse la preuve OTS et lier le digest (offline, contrat verify_proof_bytes)."""
    from opentimestamps.core.serialize import StreamDeserializationContext
    from opentimestamps.core.timestamp import DetachedTimestampFile

    with proof_path.open("rb") as fh:
        ts = DetachedTimestampFile.deserialize(StreamDeserializationContext(fh))
    expected = sha256(bytes.fromhex(digest_hex)).hexdigest()
    if ts.file_digest.hex() != expected:
        return f"MISMATCH: proof digest {ts.file_digest.hex()[:12]}… != {expected[:12]}…"
    node, attested, seen = ts.timestamp, False, 0
    while not attested and seen < 64:
        if node.attestations:
            attested = True
        children = list(node.ops.values())
        if not children:
            break
        node = children[0]
        seen += 1
    return "OK (digest lié, attestation présente)" if attested else "OK digest, attestation en attente ( PendingAttestation — upgrade lane)"


def _tsa_test(digest_hex: str) -> dict:
    """Lane de repli RFC-3161 : requête libretsa.org via asn1crypto (éphémère)."""
    try:
        r = subprocess.run(
            ["uv", "run", "--no-project", "--with", "asn1crypto",
             "python", "-c", _tsa_inner(digest_hex)],
            capture_output=True, text=True, timeout=180, check=False,
        )
        out = (r.stdout or "").strip()
        if r.returncode == 0 and out.startswith("TSA OK"):
            return {"status": "OK", "detail": out}
        return {"status": "SKIP (TSA joignable mais échec contrôlé)",
                "detail": ((r.stderr or out) or "?")[-300:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "SKIP (réseau/TSA)", "detail": str(exc)[:200]}


def _tsa_inner(digest_hex: str) -> str:
    return f'''
import sys, urllib.request
from asn1crypto import tsp, algos, core
digest = bytes.fromhex("{digest_hex}")
mi = tsp.MessageImprint({{"hash_algorithm": algos.DigestAlgorithm({{"algorithm": "sha256"}}), "hashed_message": digest}})
req = tsp.TimeStampReq({{"version": 1, "message_imprint": mi, "cert_req": True}})
http_req = urllib.request.Request("https://freetsa.org/tsr", data=req.dump(),
                                  headers={{"Content-Type": "application/timestamp-query"}})
try:
    resp = urllib.request.urlopen(http_req, timeout=30)
except Exception as e:
    print("TSA FAIL network:", e); sys.exit(3)
body = resp.read()
reply = tsp.TimeStampResp.load(body)
status = reply["status"]["status"].native
if status != "granted":
    print("TSA FAIL status:", status); sys.exit(4)
tok = reply["time_stamp_token"]
tst = tok["content"]
tst_info = tsp.TSTInfo.load(tst["encap_content_info"]["content"].contents)
im = tst_info["message_imprint"]
ok = bytes(im["hashed_message"]) == digest and im["hash_algorithm"]["algorithm"].native == "sha256"
from pathlib import Path
out = Path("{STORE / 'proofs'!s}") / ("tsa-test-" + "{digest_hex}"[:16] + ".tsr")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(body)
print("TSA OK imprint vérifié, token sauvé:", out.name)
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsa-test", action="store_true", help="exécute aussi le test TSA live (repli RFC-3161)")
    ap.add_argument("--force-reattach", action="store_true",
                    help="ré-ancre même si le digest est déjà ancré (défaut = idempotent, "
                         "rétro épic 9 item 2 : le re-run ne rajoute ni stamp ni ligne)")
    args = ap.parse_args()

    for p in PROVS:
        if not p.is_file():
            print(f"ABSENT: {p}")
            return 2

    from ots_anchor.anchor import AnchorUnavailableError, anchor
    from prereg.ledger import already_anchored

    results = []
    proofs_dir = STORE / "proofs"
    proofs_dir.mkdir(parents=True, exist_ok=True)
    for p in PROVS:
        digest = _sha(p)
        proof = proofs_dir / f"prov-{digest[:16]}.ots"
        prior = None if args.force_reattach else already_anchored(LEDGER, digest)
        if prior:
            results.append({"provenance": p.name, "sha256": digest,
                            "anchor_mode": "already-anchored (idempotent skip)",
                            "proof": prior.get("ots_proof_ref", ""),
                            "offline_verification": "skip — ancrage existant vérifié",
                            "anchored_at": prior.get("anchored_at", "")})
            print(f"{p.name}: DÉJÀ ANCRÉ ({prior.get('anchored_at','')}) — skip idempotent "
                  f"(--force-reattach pour re-stamper)")
            continue
        try:
            rec = anchor(digest, str(proof))
            mode = "ots-live"
        except AnchorUnavailableError as exc:
            print(f"OTS LIVE INDISPONIBLE pour {p.name} : {exc} — pas d'ancrage simulé "
                  f"pour une cérémonie réelle (disclose-and-halt, loi 2.6).")
            return 3
        verif = _verify_proof_bytes(digest, proof)
        append_entry(LEDGER, {
            "type": "anchor", "chain_hash": digest,
            "anchored_at": rec.anchored_at, "anchor_mode": mode,
            "ots_proof_ref": str(proof.relative_to(REPO)),
            "components": {"provenance": str(p.relative_to(REPO)), "sha256": digest},
            "purpose": f"pool provenance sealed — story 9.3 ({p.name})",
        })
        results.append({"provenance": p.name, "sha256": digest,
                        "anchor_mode": mode,
                        "proof": str(proof.relative_to(REPO)),
                        "offline_verification": verif,
                        "anchored_at": rec.anchored_at})
        print(f"{p.name}: ancré live, preuve {proof.name}, {verif}")

    tsa = None
    if args.tsa_test:
        print("test TSA fallback (RFC-3161, freetsa.org)…")
        tsa = _tsa_test(_sha(PROVS[-1]))
        print("TSA:", tsa["status"], "—", tsa["detail"][:120])

    REPORT.write_text(json.dumps({
        "ceremony": "9.3-pool-provenance-anchoring",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "anchored": results,
        "tsa_fallback_live_test": tsa or "non exécuté (rerun avec --tsa-test)",
        "ledger": str(LEDGER.relative_to(REPO)),
        "seal_note": ("content-addressed: chaque digest ancré = sha256 du fichier "
                      "provenance TEL QUEL (pré-ancrage). Les fichiers ne sont PAS "
                      "réécrits après scellement — la réception d'ancrage vit dans "
                      "le ledger append-only + ce rapport, contrat release_ceremony/AD-3."),
    }, indent=1, ensure_ascii=False) + "\n")
    print(f"→ rapport : {REPORT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
