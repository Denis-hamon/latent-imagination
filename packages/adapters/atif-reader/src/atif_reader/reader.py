"""ATIF reader adapter: reads ATIF v1.7 trajectory files/dirs (recursively),
deposits into data/landing/ as occurrence artifacts + .landing-manifest.json.
No network. Malformation containment: BOTH structural (ValueError) and
business-rule (SchemaError) violations are bucketed, never batch-fatal."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError
from core_schema.trace import ExecutionTrace


@dataclass(frozen=True)
class DepositResult:
    deposited: int
    rejected: int
    manifest_path: Path


def deposit_trajectories(
    src: Path, landing_root: Path, source_id: str, batch_id: str
) -> DepositResult:
    """Copy + validate ATIF trajectories into the landing zone."""
    src = Path(src)
    files = sorted(src.rglob("*.json")) if src.is_dir() else [src]
    batch_dir = landing_root / source_id / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    deposited: list[Path] = []
    rejected: list[tuple[str, str]] = []
    skipped: list[str] = []
    for f in files:
        if f.name == ".landing-manifest.json":
            skipped.append(f.name)
            continue
        try:
            ExecutionTrace.model_validate(json.loads(f.read_text()))
        except (ValueError, SchemaError) as e:  # structural AND business-rule violations both bucket
            rejected.append((f.name, type(e).__name__))
            continue
        dest = batch_dir / f.name
        shutil.copyfile(f, dest)
        deposited.append(dest)

    manifest = {
        "landing_manifest_version": 1,
        "origin": "atif-reader",
        "source_id": source_id,
        "batch_id": batch_id,
        "deposited": [
            {
                "path": f"{source_id}/{batch_id}/{p.name}",
                "sha256": sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }
            for p in deposited
        ],
        "rejected": [{"name": n, "error": e} for n, e in rejected],
        "skipped": skipped,
    }
    mpath = landing_root / source_id / batch_id / ".landing-manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return DepositResult(len(deposited), len(rejected), mpath)
