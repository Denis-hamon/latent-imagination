"""Deployer-local decision log (story 5.1 + CR): append-only JSONL, occurrence.

The gate writes ONLY to the deployer's own disk (FR-2 zero-custody; AD-4: the
gate never writes to any canonical store — a log path INSIDE a store root is
refused, LI-GATE-004). Lines are single `os.write` calls under an flock —
concurrent adapters never tear a line.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

from core_schema.errors import SchemaError
from core_schema.events import StoreEvent

_ALLOWED_KINDS = frozenset({"gate_annotated", "prediction_refused"})


def _inside_store_root(p: Path) -> bool:
    """Any ancestor holding a META.json marks a store root — off-limits (AD-4)."""
    cur = p.parent
    for _ in range(64):  # 64 ancestors: absurdly deep, still bounded
        if (cur / "META.json").exists():
            return True
        if cur.parent == cur:
            break
        cur = cur.parent
    return False


def append_decision(log_path: Path, event: StoreEvent) -> None:
    p = Path(log_path)
    if p.name != "decisions.jsonl":
        raise SchemaError("LI-GATE-003", "decision log must be named decisions.jsonl", {"got": str(p)})
    if event.kind not in _ALLOWED_KINDS:
        raise SchemaError("LI-GATE-003", "decision log carries gate events only",
                          {"kind": event.kind})
    if _inside_store_root(p):
        raise SchemaError("LI-GATE-004", "the gate never writes inside a store root (AD-4)",
                          {"path": str(p)})
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = (event.model_dump_json() + "\n").encode("utf-8")
        with p.open("ab") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            os.write(fh.fileno(), payload)  # one syscall — concurrent writers cannot tear
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise SchemaError("LI-GATE-005", "decision log write failed",
                          {"path": str(p), "err": type(exc).__name__}) from exc
