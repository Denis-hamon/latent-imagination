"""Tier-1 replay bundle assembly (Rosa path) — builds on 1.11 machinery."""

from __future__ import annotations

import json
from pathlib import Path

from harness.replay_export import export_bundle

LADDER = ["small", "medium", "full"]


def assemble_replay_bundle(
    out_dir: Path,
    *,
    slice_files: list[Path],
    rules_files: list[Path],
    pipeline_files: list[Path],
    inputs: dict,
    figure_id: str,
    ladder: str = "small",
) -> Path:
    """Bundle with the ladder level recorded; 'small' must always be runnable."""
    if ladder not in LADDER:
        raise ValueError(f"ladder must be one of {LADDER}")

    # pipeline gets the stranger entrypoint appended by convention
    bundle = export_bundle(
        out_dir / figure_id / ladder,
        slice_files=slice_files,
        rules_files=rules_files,
        pipeline_files=pipeline_files,
        inputs={**inputs, "ladder": ladder, "figure_id": figure_id},
    )
    manifest_path = bundle.path / "manifest.json"
    man = json.loads(manifest_path.read_text())
    man["ladder"] = ladder
    man["bundle_purpose"] = "tier1-replay"
    manifest_path.write_text(json.dumps(man, indent=2, sort_keys=True) + "\n")
    return bundle.path


def verify_mode(bundle: Path, expected_figures_json: Path):
    from harness.replay_check import replay_check

    return replay_check(bundle, expected_figures_json)
