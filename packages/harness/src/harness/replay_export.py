"""Replay bundle export — Tier-1 substrate (FR-8).

A bundle is a self-contained, content-only directory:
- slice/: the exact store slice the figure was computed from (parquet)
- rules/: the pinned rules artifacts used by the figure pipeline
- pipeline/: a verbatim COPY of the figure pipeline code + its config TOML
  (never a git reference — the stranger doesn't trust our history)
- manifest.json: layout versions, inputs block (AD-13), per-file hashes
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

LAYOUT = "replay-bundle-v1"


@dataclass(frozen=True)
class ReplayBundle:
    path: Path
    manifest: dict[str, Any]


def _hash(p: Path) -> str:
    return sha256(p.read_bytes()).hexdigest()


def export_bundle(
    out_dir: Path,
    *,
    slice_files: list[Path],
    rules_files: list[Path],
    pipeline_files: list[Path],
    inputs: dict[str, Any],
) -> ReplayBundle:
    """Copy everything into the bundle; NO clocks, NO uuids (reproducible class)."""
    out = Path(out_dir)
    for sub in ("slice", "rules", "pipeline"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    def _copy(group: str, files: list[Path]) -> list[dict[str, Any]]:
        names = [f.name for f in files]
        if len(names) != len(set(names)):
            raise ValueError(
                f"duplicate basenames in bundle group '{group}': {names} — one would clobber the other"
            )
        entries = []
        for f in files:
            dest = out / group / f.name
            shutil.copyfile(f, dest)
            entries.append({"path": f"{group}/{f.name}", "sha256": _hash(dest), "bytes": dest.stat().st_size})
        return entries

    manifest: dict[str, Any] = {
        "layout_version": LAYOUT,
        "inputs": inputs,
        "files": _copy("slice", slice_files) + _copy("rules", rules_files) + _copy("pipeline", pipeline_files),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest["bundle_hash"] = sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return ReplayBundle(out, manifest)
