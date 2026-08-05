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
        str(f.relative_to(d)): sha256(f.read_bytes()).hexdigest()
        for f in sorted(d.rglob("*")) if f.is_file()
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
    env.pop("PYTHONPATH", None)  # "" is NOT isolation (it prepends cwd). Absent var + -I isolates.
    run = bundle / "pipeline" / "run.py"
    result = subprocess.run(
        [sys.executable, "-I", str(run), "--slice", str(bundle / "slice"), "--out", str(out)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(bundle),
        check=False,  # nonzero exit is a ReplayReport, not an exception
    )
    if result.returncode != 0:
        return ReplayReport(False, ("pipeline crashed",), _env_diff())

    expected = json.loads(Path(expected_figures_json).read_text())
    produced = _hash_dir(out)
    missing_or_different = {
        name
        for name, h in expected.items()
        if produced.get(name) != h
    }
    extras = set(produced) - set(expected)  # UNKNOWN produced files are drift too
    mismatches = tuple(sorted(missing_or_different | extras))
    if mismatches:
        return ReplayReport(False, mismatches, _env_diff())
    return ReplayReport(not mismatches, mismatches, _env_diff())


def _env_diff() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }
