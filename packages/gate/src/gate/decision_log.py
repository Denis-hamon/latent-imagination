"""Deployer-local decision log (story 5.1): append-only JSONL, occurrence class.

The gate writes ONLY to the deployer's own store disk (FR-2 zero-custody; AD-4:
the gate never writes to any canonical store — this file is the ONLY write
surface of the package, and it is caller-pathed)."""

from __future__ import annotations

from pathlib import Path

from core_schema.errors import SchemaError
from core_schema.events import StoreEvent


def append_decision(log_path: Path, event: StoreEvent) -> None:
    p = Path(log_path)
    if p.name != "decisions.jsonl":
        raise SchemaError("LI-GATE-003", "decision log must be named decisions.jsonl", {"got": str(p)})
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:  # append-only, plain and honest
        fh.write(event.model_dump_json() + "\n")
