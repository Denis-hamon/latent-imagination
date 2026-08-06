"""Gate read port (story 5.1 + CR, AD-1): the gate accepts ONLY a pinned
snapshot hand-off — a directory of files + manifest copied OUT of the store.
Fail-closed on EVERY pin axis (LI-GATE-001): manifests present, parseable,
dict-shaped; layout pinned; store_version is real sha256 hex; predictor bytes
hash-checked against the caller's pin (mandatory — an unpinned load refuses);
predictor version in the supported set; corpus_version present and well-formed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError

SUPPORTED_PREDICTOR_VERSIONS = ("probe-predictor-v0",)
INTERFACE_VERSION = "gate-iface-v1"
CORPUS_VERSION_RE = re.compile(r"corpus-v(0|[1-9][0-9]*)")
_SHA_RE = re.compile(r"[0-9a-f]{64}")
STORE_LAYOUT = "store-layout-v1"


@dataclass(frozen=True)
class PinnedSnapshot:
    root: Path
    store_version: str
    predictor_hash: str
    predictor_version: str
    corpus_version: str
    manifest: dict


def _load_json_bytes(path: Path, what: str) -> tuple[bytes, dict]:
    try:
        raw = path.read_bytes()
    except OSError as exc:  # missing, unreadable, is-a-directory — all fail closed alike
        raise SchemaError("LI-GATE-001", f"pinned snapshot: {what} unreadable",
                          {"path": str(path), "err": type(exc).__name__}) from exc
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-GATE-001", f"pinned snapshot: {what} unparseable",
                          {"path": str(path)}) from exc
    if not isinstance(obj, dict):
        raise SchemaError("LI-GATE-001", f"pinned snapshot: {what} not a mapping",
                          {"path": str(path)})
    return raw, obj


def load_pinned_snapshot(root: Path, *, expected_predictor_hash: str) -> PinnedSnapshot:
    """Fail-closed load. The hash pin is MANDATORY (CR: optional pins are not pins).

    The SAME bytes are parsed and hashed — no double-read substitution window."""
    if not isinstance(expected_predictor_hash, str) or not _SHA_RE.fullmatch(expected_predictor_hash):
        raise SchemaError("LI-GATE-001", "expected_predictor_hash must be a 64-hex pin",
                          {"got": expected_predictor_hash})
    root = Path(root)
    _, meta = _load_json_bytes(root / "META.json", "META.json")
    pred_bytes, pred = _load_json_bytes(root / "predictor.json", "predictor.json")

    if meta.get("layout_version") != STORE_LAYOUT:
        raise SchemaError("LI-GATE-001", "snapshot layout_version unknown",
                          {"got": meta.get("layout_version")})
    store_version = meta.get("store_version")
    if not isinstance(store_version, str) or not _SHA_RE.fullmatch(store_version):
        raise SchemaError("LI-GATE-001", "snapshot META.store_version missing/malformed", {})
    phash = sha256(pred_bytes).hexdigest()
    if phash != expected_predictor_hash:
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
    cver = pred.get("corpus_version")
    if not isinstance(cver, str) or not CORPUS_VERSION_RE.fullmatch(cver):
        raise SchemaError("LI-GATE-001", "snapshot corpus_version missing/malformed", {"got": cver})
    return PinnedSnapshot(
        root=root, store_version=store_version, predictor_hash=phash,
        predictor_version=pver, corpus_version=cver, manifest=pred,
    )
