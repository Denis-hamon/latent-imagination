"""Offline verification: recompute and compare. NO network, ever.

Proof-level leg (deferred-work Epic-1 M-1, closed 2026-08-06): when the proof
file exists, we BYTE-PARSE it (DetachedTimestampFile.deserialize) and verify
the stamped file digest equals sha256(raw chain_hash bytes) — the ceremony's
stamping contract. Network-level Bitcoin confirmation stays the upgrade lane.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from prereg.anchor_format import AnchorRecord, VerifyReport
from prereg.chain import ChainManifest


def verify_offline(manifest: ChainManifest, record: AnchorRecord) -> VerifyReport:
    errors: list[str] = []
    if manifest.chain_hash != record.chain_hash:
        errors.append(
            f"chain_hash mismatch: manifest {manifest.chain_hash[:12]}… vs anchored {record.chain_hash[:12]}…"
        )
    if not record.ots_proof_ref:
        errors.append("empty ots_proof_ref")
    return VerifyReport(ok=not errors, errors=tuple(errors))


def verify_proof_bytes(manifest: ChainManifest, proof_path: Path) -> VerifyReport:
    """Byte-parse the .ots and bind it to the chain (offline; no calendar call)."""
    errors: list[str] = []
    p = Path(proof_path)
    if not p.is_file():
        return VerifyReport(ok=False, errors=(f"proof missing: {p}",))
    try:
        from opentimestamps.core.serialize import StreamDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile

        with p.open("rb") as fh:
            ts = DetachedTimestampFile.deserialize(StreamDeserializationContext(fh))
    except ImportError:
        return VerifyReport(ok=False, errors=("opentimestamps-client not installed (mvp extra)",))
    except (ValueError, OSError) as exc:
        # byte-level corruption is a verify FAILURE, not a crash; opentimestamps'
        # deserialize raises its own subclasses of ValueError on bad structure
        return VerifyReport(ok=False, errors=(f"proof unparseable ({type(exc).__name__})",))
    expected = sha256(bytes.fromhex(manifest.chain_hash)).hexdigest()
    if ts.file_digest.hex() != expected:
        errors.append(
            f"proof digest {ts.file_digest.hex()[:12]}… != sha256(chain bytes) {expected[:12]}…"
        )
    # attestations live at the leaf of the op-chain (OTS tree), not the root
    node = ts.timestamp
    found_attestation = False
    seen = 0
    while not found_attestation and seen < 64:
        if node.attestations:
            found_attestation = True
            break
        children = list(node.ops.values())
        if not children:
            break
        node = children[0]
        seen += 1
    if not found_attestation:
        errors.append("proof carries no attestation")
    return VerifyReport(ok=not errors, errors=tuple(errors))
