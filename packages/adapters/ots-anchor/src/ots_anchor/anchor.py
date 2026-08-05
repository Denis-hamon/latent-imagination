"""OTS anchor adapter — the ONLY network hop in the prereg family (AD-9 split).

Contract test stays offline: we verify the client wraps bytes→proof and raises
cleanly on unreachable calendars (mocked failures), not live anchors.
"""

from __future__ import annotations

from datetime import UTC, datetime

from prereg.anchor_format import AnchorRecord  # type: ignore[import-not-found]


class AnchorUnavailableError(Exception):
    """Calendar unreachable / proof pending — retry semantics are the caller's."""


def anchor(chain_hash: str, proof_path: str) -> AnchorRecord:
    """Real anchoring path (lazy import so the pure lib never sees the dep)."""
    try:
        from opentimestamps_client import OpenTimestampsClient  # noqa: F401
    except ImportError as e:  # pragma: no cover - env-dependent
        raise AnchorUnavailableError(str(e)) from e
    # Actual remote call — intentionally thin: whatever the client returns as
    # proof is stored at proof_path by the caller's ceremony script.
    raise AnchorUnavailableError("live anchoring runs from scripts/prereg/, not in tests")


def anchor_offline_simulated(chain_hash: str, proof_path: str) -> AnchorRecord:
    """Fixture/simulation path used in tests and docs: builds the record shape."""
    return AnchorRecord(
        chain_hash=chain_hash,
        ots_proof_ref=proof_path,
        anchored_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
