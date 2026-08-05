"""Anchor record format — OCCURRENCE artifact (AD-7: timestamps allowed here)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnchorRecord:
    """An external time-anchor (OTS or RFC-3161) bound to a chain_hash."""

    chain_hash: str
    ots_proof_ref: str  # path/URI of the proof file (or upgrade receipt)
    anchored_at: str    # ISO-8601 UTC — allowed: occurrence class

    def to_dict(self) -> dict[str, str]:
        return {
            "chain_hash": self.chain_hash,
            "ots_proof_ref": self.ots_proof_ref,
            "anchored_at": self.anchored_at,
        }


@dataclass(frozen=True)
class VerifyReport:
    ok: bool
    errors: tuple[str, ...] = ()
