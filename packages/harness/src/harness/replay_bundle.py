"""Tier-1 replay bundle assembly (Rosa path) — builds on 1.11 machinery."""

from __future__ import annotations

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
    """Bundle with the ladder level recorded in inputs BEFORE the bundle hash is
    computed — the sealed hash always covers the final manifest (C2 fix)."""
    if ladder not in LADDER:
        raise ValueError(f"ladder must be one of {LADDER}")

    bundle = export_bundle(
        out_dir / figure_id / ladder,
        slice_files=slice_files,
        rules_files=rules_files,
        pipeline_files=pipeline_files,
        inputs={**inputs, "ladder": ladder, "figure_id": figure_id},
    )
    return bundle.path


def verify_mode(bundle: Path, expected_figures_json: Path):
    from harness.replay_check import replay_check

    return replay_check(bundle, expected_figures_json)
