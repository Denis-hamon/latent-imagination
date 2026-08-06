"""Gate read port (story 5.1, AD-1): the gate accepts ONLY a pinned snapshot
hand-off — a directory of files + manifest copied OUT of the store. There is
no API to read a live store, by construction: this module takes a PATH and
proves the pin before any byte of predictor is touched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError

SUPPORTED_PREDICTOR_VERSIONS = ("probe-predictor-v0",)
INTERFACE_VERSION = "gate-iface-v1"


@dataclass(frozen=True)
class PinnedSnapshot:
    root: Path
    store_version: str
    predictor_hash: str
    predictor_version: str
    corpus_version: str
    manifest: dict


def _sha(p: Path) -> str:
    return sha256(p.read_bytes()).hexdigest()


def load_pinned_snapshot(root: Path, *, expected_predictor_hash: str | None = None) -> PinnedSnapshot:
    """Fail-closed load (LI-GATE-001 on any pin violation)."""
    root = Path(root)
    meta_p = root / "META.json"
    pred_p = root / "predictor.json"
    try:
        meta = json.loads(meta_p.read_text())
        pred = json.loads(pred_p.read_text())
    except FileNotFoundError as exc:
        raise SchemaError("LI-GATE-001", "pinned snapshot incomplete (META.json / predictor.json)",
                          {"missing": str(exc.filename)}) from exc
    except ValueError as exc:
        raise SchemaError("LI-GATE-001", "pinned snapshot manifest unparseable", {}) from exc
    store_version = meta.get("store_version")
    if not isinstance(store_version, str) or len(store_version) != 64:
        raise SchemaError("LI-GATE-001", "snapshot META.store_version missing/malformed", {})
    phash = _sha(pred_p)
    if expected_predictor_hash is not None and phash != expected_predictor_hash:
        raise SchemaError(
            "LI-GATE-001", "predictor hash mismatch — the pin is the whole point",
            {"expected": expected_predictor_hash, "actual": phash},
        )
    pver = pred.get("predictor_version")
    if pver not in SUPPORTED_PREDICTOR_VERSIONS:
        raise SchemaError(
            "LI-GATE-001", "unsupported predictor version",
            {"got": pver, "supported": list(SUPPORTED_PREDICTOR_VERSIONS)},
        )
    cver = pred.get("corpus_version", "corpus-v0")
    return PinnedSnapshot(
        root=root, store_version=store_version, predictor_hash=phash,
        predictor_version=pver, corpus_version=cver, manifest=pred,
    )
