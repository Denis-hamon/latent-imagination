"""E2E (Story 1.3 AC2): a third party reproduces a fixture figure from a store
using ONLY the layout contract + duckdb — zero project imports.

This test is intentionally written as if by someone who has never read our code:
it follows store-layout-v1/README.md mechanically. It builds its own tiny store
on disk by hand (writing parquet + manifest files per the contract) rather than
using our emit helpers — that's what makes it a genuine consumer-side check.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

LAYOUT_VERSION = "store-layout-v1"


def _hand_built_store(root: Path) -> None:
    """Writes a minimal contract-valid store WITHOUT importing project code."""
    snap_dir = root / "canonical" / "snapshots" / "v-test"
    snap_dir.mkdir(parents=True)
    table = pa.table({"attempt_id": ["a1", "a2"], "flipped": [True, False]})
    pq.write_table(table, snap_dir / "part-0.parquet")

    file_bytes = (snap_dir / "part-0.parquet").read_bytes()
    manifest = {
        "layout_version": LAYOUT_VERSION,
        "artifact_id": "snap-001",
        "artifact_type": "canonical-snapshot",
        "artifact_version": "v-test",
        "artifact_class": "reproducible",
        "producer": "traces-ingest",
        "inputs": {"store_snapshot": "x" * 64, "ruleset_version": "rules-v1", "code_commit": "c" * 40, "seeds": {}},
        "files": [
            {
                "path": "canonical/snapshots/v-test/part-0.parquet",
                "sha256": sha256(file_bytes).hexdigest(),
                "bytes": len(file_bytes),
            }
        ],
    }
    man_dir = root / "canonical" / "manifests"
    man_dir.mkdir(parents=True)
    (man_dir / "snap-001.v-test.artifact.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True)
    )

    hashes = [sha256(file_bytes).hexdigest()]
    store_version = sha256(
        json.dumps(sorted(hashes), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (root / "META.json").write_text(
        json.dumps({"layout_version": LAYOUT_VERSION, "store_version": store_version}, indent=2, sort_keys=True)
    )


def test_stranger_reproduces_figure_with_duckdb_only(tmp_path: Path):
    root = tmp_path / "store"
    root.mkdir()
    _hand_built_store(root)

    rows = duckdb.sql(
        f"select avg(case when flipped then 1.0 else 0.0 end) as erbve from read_parquet('{root}/canonical/snapshots/*/*.parquet')"
    ).fetchall()
    assert rows[0][0] == 0.5

    # store_version recomputation from raw files, following the README rule only
    canon = root / "canonical"
    hashes = sorted(
        sha256(f.read_bytes()).hexdigest()
        for f in sorted(canon.rglob("*"))
        if f.is_file() and f.suffix != ".json"
    )
    recomputed = sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    meta = json.loads((root / "META.json").read_text())
    assert recomputed == meta["store_version"]
