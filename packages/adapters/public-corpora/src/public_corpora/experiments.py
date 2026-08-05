"""Featch public corpora for the NEGATIVE class: SWE-smith trajectories (MIT).

Every row = one real agent trajectory with its final patch and its `resolved`
flag — real failures (resolved=false) on real OSS repos, which is exactly the
non-toy negative class the amendment requires.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx

HF_REPO = "SWE-bench/SWE-smith-trajectories"
PARQUET_LIST = f"https://huggingface.co/api/datasets/{HF_REPO}/parquet/default/ticks"


def fetch_smith_negatives(
    landing_root: Path,
    *,
    client: httpx.Client | None = None,
    shards: int = 1,
    batch_id: str = "smith-neg-v1",
) -> dict:
    """Download N shards of SWE-smith trajectories; land raw + a normalized digest
    of (instance_id, model, patch, resolved) for resolved=false attempts.
    """
    client = client or httpx.Client(timeout=300.0, follow_redirects=True)
    batch_dir = Path(landing_root) / "swe-smith-trajectories" / batch_id
    (batch_dir / "raw").mkdir(parents=True, exist_ok=True)

    r = client.get(PARQUET_LIST)
    r.raise_for_status()
    payload = r.json()
    urls = [f["url"] if isinstance(f, dict) else f for f in payload][:shards]

    import duckdb

    negatives: list[dict[str, Any]] = []
    landed: list[Path] = []
    for i, u in enumerate(urls):
        dest = batch_dir / "raw" / f"ticks-{i:05d}.parquet"
        if not dest.exists():
            rr = client.get(u)
            rr.raise_for_status()
            dest.write_bytes(rr.content)
        landed.append(dest)
        rows = duckdb.sql(
            f"""select instance_id, model, patch, resolved
                from read_parquet('{dest}')
                where resolved = false and patch is not null and length(patch) > 10"""
        ).fetchall()
        for iid, model, patch, resolved in rows:
            negatives.append(
                {
                    "instance_id": iid,
                    "model": model,
                    "patch": patch,
                    "resolved": False,
                    "source": HF_REPO,
                }
            )

    items_path = batch_dir / "negative-items.json"
    items_path.write_text(json.dumps(negatives, indent=0, sort_keys=True) + "\n")
    manifest = {
        "landing_manifest_version": 1,
        "origin": "public-corpora/swe-smith-trajectories",
        "batch_id": batch_id,
        "deposited": [
            {"path": str(p.relative_to(batch_dir)), "sha256": sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
            for p in [*landed, items_path]
        ],
        "negative_count": len(negatives),
        "shards": len(landed),
    }
    (batch_dir / ".landing-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest

