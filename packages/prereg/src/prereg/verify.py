"""Offline verification: recompute and compare. NO network, ever."""

from __future__ import annotations

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
