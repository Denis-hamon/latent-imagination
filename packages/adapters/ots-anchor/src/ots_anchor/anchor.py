"""OTS anchor adapter — the ONLY network hop in the prereg family (AD-9 split).

Uses opentimestamps-client 0.7.2 pinned. The 0.7.2 packages are ``otsclient`` /
``opentimestamps`` (lib 0.4.5) and the CLI is the ``ots`` console script —
there is NO importable ``ots`` module (deferred-work Epic-1 entry closed
2026-08-06: ``python -m ots`` could never work).
"""

from __future__ import annotations

import shutil
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
    # Live path: invoke the ots console script (cleaner than the lib's
    # argparse-driven client code). Probe PATH honestly: no script, no live.
    ots_bin = shutil.which("ots")  # pragma: no cover - env-dependent
    if ots_bin is None:  # pragma: no cover - env-dependent
        raise AnchorUnavailableError("ots console script not on PATH (opentimestamps-client 0.7.2)")

    import subprocess

    prof = Path(proof_path)
    prof.parent.mkdir(parents=True, exist_ok=True)
    (prof.with_suffix(".data.bin")).write_bytes(bytes.fromhex(chain_hash))
    r = subprocess.run(
        [ots_bin, "stamp", prof.with_suffix(".data.bin")],  # 0.7.2: FILE is positional (no -i)
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
