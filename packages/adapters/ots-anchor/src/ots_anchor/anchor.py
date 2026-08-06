"""OTS anchor adapter — the ONLY network hop in the prereg family (AD-9 split).

Uses opentimestamps-client 0.7.2 pinned. Module names: ``otsclient`` /
``opentimestamps`` (verified live on the node 2026-08-05).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from prereg.anchor_format import AnchorRecord  # type: ignore[import-not-found]


class AnchorUnavailableError(Exception):
    """Calendar unreachable / proof pending — retry semantics are the caller's."""


def anchor(chain_hash: str, proof_path: str) -> AnchorRecord:
    """Live OTS anchor via the actual client; unreachable calendar raises cleanly.

    The OTS flow submits the digest and calendars queue it — the downloadable
    proof needs a confirmation round. We stamp now and record; the caller may
    upgrade the proof later (OTS upgrade flow).
    """
    try:
        from opentimestamps.core import Op, OpSHA256  # noqa: F401
        from opentimestamps.core.timestamp import DetachedTimestampFile  # noqa: F401
        from otsclient.args import create  # noqa: F401
    except ImportError as e:  # pragma: no cover - env-dependent
        raise AnchorUnavailableError(str(e)) from e

    # Live path: invoke the ots CLI via subprocess (cleaner than the lib's
    # argparse-driven client code).
    import subprocess
    import sys

    prof = Path(proof_path)
    prof.parent.mkdir(parents=True, exist_ok=True)
    (prof.with_suffix(".data.bin")).write_bytes(bytes.fromhex(chain_hash))
    r = subprocess.run(
        [sys.executable, "-m", "ots", "stamp", "-i", prof.with_suffix(".data.bin")],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise AnchorUnavailableError(r.stderr[-400:])
    # ots wrote <file>.data.bin.ots
    ots_file = prof.with_suffix(".data.bin.ots")
    if ots_file.exists():
        prof.write_bytes(ots_file.read_bytes())
        ots_file.unlink()
        prof.with_suffix(".data.bin").unlink()
    return AnchorRecord(
        chain_hash=chain_hash,
        ots_proof_ref=str(prof),
        anchored_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


def anchor_offline_simulated(chain_hash: str, proof_path: str) -> AnchorRecord:
    """Fixture/simulation path used in tests and docs: builds the record shape."""
    return AnchorRecord(
        chain_hash=chain_hash,
        ots_proof_ref=proof_path,
        anchored_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
