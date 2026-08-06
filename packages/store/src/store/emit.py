"""Write helpers — the ONLY way artifacts enter the store (AD-4).

See store-layout-v1/README.md. Additional hardening (review 2026-08-05):
- duplicate basenames within one write are rejected
- same id+version re-emitted with IDENTICAL content = no-op (idempotent ingest);
  different content = hard failure (append-only)
- artifact ids/versions are slug-checked (no path traversal)
- reproducible manifests reject created_at; inputs block mandatory (AD-13)
- manifest dir layout is zone-scoped: <zone>/manifests/<id>.<version>.artifact.json
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from store.layout import LAYOUT_VERSION, REPRODUCIBLE_CLASSES


class StoreWriteError(Exception):
    """LI-STORE-001 class: any contract violation at write time."""


WRITERS: dict[str, tuple[str, ...]] = {
    "traces-ingest": ("canonical-snapshot",),
    "labeling": ("labels", "quarantine"),
    "harness": ("figure", "bundle"),
    "prereg": ("prereg-commit",),
    "publication": ("release-manifest",),
    "corpus": ("corpus-item-set",),
}

_DIR_BY_TYPE = {
    "canonical-snapshot": "canonical",
    "labels": "labels",
    "quarantine": "quarantine",
    "figure": "figures",
    "bundle": "bundles",
    "prereg-commit": "prereg",
    "release-manifest": "releases",
    # corpus item-sets are reproducible and live in canonical/ so the
    # content-addressed store_version covers them (AD-13 citations hold).
    "corpus-item-set": "canonical",
}

_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _check_slug(value: str, what: str) -> None:
    if not _SLUG.match(value):
        raise StoreWriteError(
            f"LI-STORE-005: invalid {what} {value!r} (slug policy: no traversal, no uppercase)"
        )


@dataclass(frozen=True)
class WrittenArtifact:
    artifact_dir: Path
    manifest_path: Path
    manifest: dict[str, Any]


def _sha256_file(p: Path) -> str:
    h = sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):  # stream large artifacts
            h.update(chunk)
    return h.hexdigest()


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_store_version(store_root: Path) -> str:
    """Content-addressed store identity (deterministic; empty set → constant)."""
    from store.layout import EMPTY_STORE_VERSION

    canon_dir = store_root / "canonical"
    hashes: list[str] = []
    if canon_dir.is_dir():
        for f in sorted(canon_dir.rglob("*")):
            # manifests are index metadata; artifact CONTENT (parquet AND json,
            # e.g. leakage-audit.json) feeds the store identity (CR 4.2 fix:
            # audit tampering must move the version).
            if f.is_file() and "manifests" not in f.relative_to(canon_dir).parts:
                hashes.append(_sha256_file(f))
    if not hashes:
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
    _check_slug(artifact_id, "artifact_id")
    _check_slug(artifact_version, "artifact_version")

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
    elif created_at is None:
        created_at = datetime.now(UTC).isoformat()

    files = [Path(f) for f in files]
    names = [f.name for f in files]
    if len(names) != len(set(names)):
        raise StoreWriteError(
            "LI-STORE-006: duplicate basenames in one write would silently clobber content"
        )
    for f in files:
        if not f.is_file():
            raise StoreWriteError(f"LI-STORE-007: missing file {f}")

    zone = store_root / _DIR_BY_TYPE[artifact_type]
    artifact_dir = zone / artifact_id / artifact_version
    manifests_zone = zone / "manifests"
    manifest_path = manifests_zone / f"{artifact_id}.{artifact_version}.artifact.json"

    new_entries = []
    for src in files:
        new_entries.append(
            {
                "path": str((artifact_dir / src.name).relative_to(store_root)),
                "sha256": _sha256_file(src),
                "bytes": src.stat().st_size,
            }
        )

    if artifact_dir.exists() or manifest_path.exists():
        # idempotent same-content re-write is OK; different content must fail.
        if manifest_path.exists():
            old = json.loads(manifest_path.read_text())
            same = all(
                oe["sha256"] == ne["sha256"] and oe["path"] == ne["path"]
                for oe, ne in zip(old.get("files", []), new_entries, strict=False)
            ) and len(old.get("files", [])) == len(new_entries)
            if same:
                # Same bytes, DIFFERENT inputs claim = a different artifact
                # pretending to be this version (4.3 CR). store_snapshot moves
                # naturally as the store grows, so it is exempt from the compare.
                old_inputs = {k: v for k, v in (old.get("inputs") or {}).items()
                              if k != "store_snapshot"}
                new_inputs = {k: v for k, v in (inputs or {}).items()
                              if k != "store_snapshot"}
                if old_inputs != new_inputs:
                    raise StoreWriteError(
                        "LI-STORE-008: same content, different inputs — bump artifact_version "
                        "(inputs are part of the artifact's claim)"
                    )
                base = artifact_dir if artifact_dir.exists() else None
                return WrittenArtifact(
                    artifact_dir=base or artifact_dir,
                    manifest_path=manifest_path,
                    manifest=old,
                )
        raise StoreWriteError(
            f"LI-STORE-004: append-only violation — {artifact_dir} already exists with different content"
        )

    artifact_dir.mkdir(parents=True)
    for src in files:
        dest = artifact_dir / src.name
        dest.write_bytes(src.read_bytes())

    manifest: dict[str, Any] = {
        "layout_version": LAYOUT_VERSION,
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "artifact_version": artifact_version,
        "artifact_class": artifact_class,
        "producer": stage,
        "inputs": inputs,
        "files": new_entries,
    }
    if artifact_class == "occurrence":
        manifest["created_at"] = created_at

    manifests_zone.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    _write_meta(store_root)
    return WrittenArtifact(
        artifact_dir=artifact_dir, manifest_path=manifest_path, manifest=manifest
    )
