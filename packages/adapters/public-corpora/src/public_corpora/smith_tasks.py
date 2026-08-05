"""Join negatives to their task statements (SWE-smith dataset, MIT)."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import httpx

SMITH_TASKS = "https://huggingface.co/api/datasets/SWE-bench/SWE-smith/parquet/default/train"


def fetch_smith_task_statements(
    landing_root: Path,
    *,
    client: httpx.Client | None = None,
    max_shards: int = 3,
    batch_id: str = "smith-tasks-v1",
) -> dict:
    client = client or httpx.Client(timeout=300.0, follow_redirects=True)
    batch_dir = Path(landing_root) / "swe-smith-tasks" / batch_id
    (batch_dir / "raw").mkdir(parents=True, exist_ok=True)

    r = client.get(SMITH_TASKS)
    r.raise_for_status()
    urls = [u if isinstance(u, str) else u["url"] for u in r.json()][:max_shards]

    import duckdb

    landed: list[Path] = []
    joined: dict[str, str] = {}
    for i, u in enumerate(urls):
        dest = batch_dir / "raw" / f"train-{i:05d}.parquet"
        if not dest.exists():
            rr = client.get(u)
            rr.raise_for_status()
            dest.write_bytes(rr.content)
        landed.append(dest)
        rows = duckdb.sql(
            f"""select instance_id, problem_statement from read_parquet('{dest}')"""
        ).fetchall()
        for iid, ps in rows:
            joined[iid] = ps

    out_path = batch_dir / "task-statements.json"
    out_path.write_text(json.dumps(joined, sort_keys=True) + "\n")
    manifest = {
        "origin": "public-corpora/swe-smith-tasks",
        "batch_id": batch_id,
        "deposited": [
            {"path": str(p.relative_to(batch_dir)), "sha256": sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
            for p in [*landed, out_path]
        ],
        "task_count": len(joined),
    }
    (batch_dir / ".landing-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
