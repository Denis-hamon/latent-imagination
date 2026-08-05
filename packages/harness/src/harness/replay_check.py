"""Replay check: re-execute a bundle and compare against expected hashes.

Runs the bundle's own `pipeline/run.py` in a subprocess with an env whose only
imports are the bundle's slice + rules (plus whatever the caller allows).
Default comparison = byte-identical (zero-tolerance default, pre-registered).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class ReplayReport:
    ok: bool
    mismatches: tuple[str, ...]
    env_diff: dict[str, str] | None


def _hash_dir(d: Path) -> dict[str, str]:
    return {
        f.name: sha256(f.read_bytes()).hexdigest()
        for f in sorted(d.glob("*")) if f.is_file()
    }


def replay_check(bundle: Path, expected_figures_json: Path) -> ReplayReport:
    bundle = Path(bundle)
    out = bundle / "out"
    if out.exists():
        shutil_target = out
        import shutil as _s

        _s.rmtree(shutil_target)
    out.mkdir()

    env = os.environ.copy()
    env["PYTHONPATH"] = ""  # project sources invisible to the recompute
    run = bundle / "pipeline" / "run.py"
    result = subprocess.run(
        [sys.executable, str(run), "--slice", str(bundle / "slice"), "--out", str(out)],
        capture_output=True,
        text=True,
        env=env,
        check=False,  # nonzero exit is a ReplayReport, not an exception
    )
    if result.returncode != 0:
        return ReplayReport(False, ("pipeline crashed",), _env_diff())

    expected = json.loads(Path(expected_figures_json).read_text())
    produced = _hash_dir(out)
    mismatches = tuple(
        name
        for name, h in expected.items()
        if produced.get(name) != h
    )
    return ReplayReport(not mismatches, mismatches, _env_diff())


def _env_diff() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }
