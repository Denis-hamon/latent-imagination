"""Fetch SWE-smith trajectories (MIT) — the REAL non-toy classes.

Two modes:
- negatives-only (resolved=false): real agent failures
- matched: resolved=true + false from the SAME corpus/models/instances — the
  watermark-killer control; style learns nothing from provenance there.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx

HF_REPO = "SWE-bench/SWE-smith-trajectories"


def _shard_urls(n: int) -> list[str]:
    return [
        f"https://huggingface.co/datasets/{HF_REPO}/resolve/main/data/ticks-0000{i}-of-00008.parquet"
        for i in range(n)
    ]


def _fetch(landing_root: Path, shard_count: int, only_negatives: bool, batch_id: str) -> dict:
    client = httpx.Client(timeout=300.0, follow_redirects=True)
    batch_dir = Path(landing_root) / "swe-smith-trajectories" / batch_id
    (batch_dir / "raw").mkdir(parents=True, exist_ok=True)

    import duckdb

    items: list[dict[str, Any]] = []
    landed: list[Path] = []
    for i, url in enumerate(_shard_urls(shard_count)):
        dest = batch_dir / "raw" / f"ticks-{i:05d}.parquet"
        if not dest.exists():
            r = client.get(url)
            r.raise_for_status()
            dest.write_bytes(r.content)
        landed.append(dest)
        flt = "where patch is not null and length(patch) > 10"
        if only_negatives:
            flt += " and resolved = false"
        rows = duckdb.sql(
            f"""select instance_id, model, patch, resolved from read_parquet('{dest}') {flt}"""
        ).fetchall()
        for iid, model, patch, resolved in rows:
            items.append(
                {
                    "instance_id": iid,
                    "model": model,
                    "patch": patch,
                    "resolved": bool(resolved),
                    "source": HF_REPO,
                }
            )

    digest_name = "negative-items.json" if only_negatives else "matched-items.json"
    digest = batch_dir / digest_name
    digest.write_text(json.dumps(items, indent=0, sort_keys=True) + "\n")
    manifest = {
        "landing_manifest_version": 1,
        "origin": "public-corpora/swe-smith-trajectories",
        "batch_id": batch_id,
        "deposited": [
            {"path": str(p.relative_to(batch_dir)), "sha256": sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
            for p in [*landed, digest]
        ],
        "item_count": len(items),
        "mode": "negatives-only" if only_negatives else "matched resolved±",
        "shards": len(landed),
    }
    (batch_dir / ".landing-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def fetch_smith_negatives(landing_root: Path, *, shards: int = 1, batch_id: str = "smith-neg-v1") -> dict:
    return _fetch(landing_root, shards, True, batch_id)


def fetch_smith_matched(landing_root: Path, *, shards: int = 2, batch_id: str = "smith-matched-v1") -> dict:
    """Positives AND negatives from the same corpus — the watermark control."""
    return _fetch(landing_root, shards, False, batch_id)
