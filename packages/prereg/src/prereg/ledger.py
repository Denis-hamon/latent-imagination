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


def run_entry(run_id: str, started_at: str, ruleset_hash: str, store_version: str) -> dict[str, Any]:
    return {
        "type": "run",
        "run_id": run_id,
        "started_at": started_at,
        "ruleset_hash": ruleset_hash,
        "store_version": store_version,
    }
