"""Ledger append — the prereg-ledger.jsonl writer. Pure: caller supplies the path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_entry(ledger_path: Path, entry: dict[str, Any]) -> None:
    """Append one jsonl row. Entry must already be fully formed (timestamps by
    the caller — ledger rows are occurrence metadata)."""
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def anchor_entry(chain_hash: str, ruleset_hash: str, anchored_at: str, proof_ref: str) -> dict[str, Any]:
    return {
        "type": "anchor",
        "chain_hash": chain_hash,
        "ruleset_hash": ruleset_hash,
        "anchored_at": anchored_at,
        "ots_proof_ref": proof_ref,
    }


_ANCHOR_TYPES = ("anchor", "window-approved", "prereg-package",
                 "prereg-package-amendment", "verdict")


def already_anchored(ledger_path: Path, chain_hash: str) -> dict[str, Any] | None:
    """Idempotence de cérémonie (rétro épic 9 item 2) : une ligne d'ancrage
    existe-t-elle déjà pour ce digest ? Re-stamper un digest déjà ancré est
    légales mais bruyant (doublons d'occurrence) ; le caller décide de skipper
    (défaut) ou de forcer (ré-ancrage explicite). Malformé = ignoré/compté,
    jamais crashé (loi poison 5.6)."""
    p = Path(ledger_path)
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("type") in _ANCHOR_TYPES and entry.get("chain_hash") == chain_hash:
            return entry
    return None


def run_entry(run_id: str, started_at: str, ruleset_hash: str, store_version: str) -> dict[str, Any]:
    return {
        "type": "run",
        "run_id": run_id,
        "started_at": started_at,
        "ruleset_hash": ruleset_hash,
        "store_version": store_version,
    }


def certificate_entry(
    certificate_hash: str,
    direction: str,
    verdict_hash: str,
    generations: list[str] | tuple[str, ...],
    certified_precision: float,
    registered_bar: float,
    issued_at: str,
    anchored_at: str,
    *,
    anchor_mode: str,
    proof_ref: str,
    purpose: str,
    supersedes: str | None = None,
    supersession_reason: str | None = None,
) -> dict[str, Any]:
    """Occurrence row for certificate issuance/supersession (Story 7.1, FR-21).

    Timestamps caller-supplied (occurrence metadata). Supersession never
    deletes or edits prior rows — it appends a row that names the revoked
    certificate by hash (AD-3, erratum protocol).
    """
    row: dict[str, Any] = {
        "type": "certificate",
        "certificate_hash": certificate_hash,
        "direction": direction,
        "verdict_hash": verdict_hash,
        "generations": list(generations),
        "certified_precision": certified_precision,
        "registered_bar": registered_bar,
        "issued_at": issued_at,
        "anchored_at": anchored_at,
        "anchor_mode": anchor_mode,
        "ots_proof_ref": proof_ref,
        "purpose": purpose,
    }
    if supersedes is not None:
        row["supersedes"] = supersedes
    if supersession_reason is not None:
        row["supersession_reason"] = supersession_reason
    return row
