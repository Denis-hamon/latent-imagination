"""Write helpers — the ONLY way artifacts enter the store (AD-4).

Thin by design (AD-8): one function, a WRITERS ownership table (edit = one row,
reviewed), and a manifest format governed by store-layout-v1/README.md.

Rules enforced here:
- append-only: overwriting an existing artifact path raises
- ownership: only the stage owning the artifact_type may write it
- AD-7 hygiene: reproducible manifests carry no ``created_at``/uuid
- AD-13 covenant: reproducible artifacts carry an ``inputs`` block
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from store.layout import LAYOUT_VERSION, REPRODUCIBLE_CLASSES


class StoreWriteError(Exception):
    """LI-STORE-001 class: any contract violation at write time."""


# AD-4: the ownership table. Edit = one row, reviewed like an AD change.
WRITERS: dict[str, tuple[str, ...]] = {
    "traces-ingest": ("canonical-snapshot",),
    "labeling": ("labels", "quarantine"),
    "harness": ("figure", "bundle"),
    "prereg": ("prereg-commit",),
    "publication": ("release-manifest",),
}

_DIR_BY_TYPE = {
    "canonical-snapshot": "canonical",
    "labels": "labels",
    "quarantine": "quarantine",
    "figure": "figures",
    "bundle": "bundles",
    "prereg-commit": "prereg",
    "release-manifest": "releases",
}


@dataclass(frozen=True)
class WrittenArtifact:
    artifact_dir: Path
    manifest_path: Path
    manifest: dict[str, Any]


def _sha256_file(p: Path) -> str:
    return sha256(p.read_bytes()).hexdigest()


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_store_version(store_root: Path) -> str:
    """Content-addressed store identity: sha256 over the canonical-JSON list of
    sorted content hashes of every canonical snapshot file. Empty set → the
    documented constant (sha256 of "[]"). Deterministic (no clock, no fs order)."""
    canon_dir = store_root / "canonical"
    hashes: list[str] = []
    if canon_dir.is_dir():
        for f in sorted(canon_dir.rglob("*")):
            if f.is_file() and f.suffix != ".json":  # parquet/data files only
                hashes.append(_sha256_file(f))
    if not hashes:
        from store.layout import EMPTY_STORE_VERSION

        return EMPTY_STORE_VERSION
    return sha256(_canon(sorted(hashes)).encode("utf-8")).hexdigest()


def _write_meta(store_root: Path) -> None:
    store_root.mkdir(parents=True, exist_ok=True)
    meta = {
        "layout_version": LAYOUT_VERSION,
        "store_version": compute_store_version(store_root),
    }
    (store_root / "META.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_artifact(
    stage: str,
    artifact_type: str,
    artifact_id: str,
    artifact_version: str,
    files: Iterable[Path],
    inputs: dict[str, Any] | None,
    store_root: Path,
    *,
    created_at: str | None = None,
) -> WrittenArtifact:
    """Write an artifact + manifest into the store under the contract."""
    owned = WRITERS.get(stage, ())
    if artifact_type not in owned:
        raise StoreWriteError(
            f"LI-STORE-001: stage '{stage}' may not write artifact_type "
            f"'{artifact_type}' (owned by: "
            f"{[s for s, t in WRITERS.items() if artifact_type in t] or 'nobody'})"
        )

    artifact_class = (
        "reproducible" if artifact_type in REPRODUCIBLE_CLASSES else "occurrence"
    )
    if artifact_class == "reproducible":
        if created_at is not None:
            raise StoreWriteError(
                "LI-STORE-002: reproducible manifests must not carry created_at (AD-7)"
            )
        if inputs is None:
            raise StoreWriteError(
                "LI-STORE-003: reproducible artifacts must carry an inputs block (AD-13)"
            )
    else:
        if created_at is None:
            created_at = datetime.now(_utc()).isoformat()

    zone = store_root / _DIR_BY_TYPE[artifact_type]
    artifact_dir = zone / artifact_id / artifact_version
    if artifact_dir.exists():
        raise StoreWriteError(
            f"LI-STORE-004: append-only violation — {artifact_dir} already exists"
        )
    artifact_dir.mkdir(parents=True)

    file_entries = []
    for src in files:
        src = Path(src)
        dest = artifact_dir / src.name
        dest.write_bytes(src.read_bytes())
        file_entries.append(
            {"path": str(dest.relative_to(store_root)), "sha256": _sha256_file(dest), "bytes": dest.stat().st_size}
        )

    manifest: dict[str, Any] = {
        "layout_version": LAYOUT_VERSION,
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "artifact_version": artifact_version,
        "artifact_class": artifact_class,
        "producer": stage,
        "inputs": inputs,
        "files": file_entries,
    }
    if artifact_class == "occurrence":
        manifest["created_at"] = created_at

    manifests_zone = zone / "manifests"
    manifests_zone.mkdir(exist_ok=True)
    manifest_path = manifests_zone / f"{artifact_id}.{artifact_version}.artifact.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    _write_meta(store_root)
    return WrittenArtifact(
        artifact_dir=artifact_dir, manifest_path=manifest_path, manifest=manifest
    )


def _utc():

    return UTC
