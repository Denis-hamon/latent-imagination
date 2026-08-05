"""Public corpora adapter: fetch SWE-bench-family metadata into data/landing/.

Network is allowed HERE (edge adapter). Supported sources (v1): SWE-bench
Verified via HF datasets-server parquet export. Items are written as
`*.corpus.json` deposits — metric-side readers never hit the network.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import httpx

HF_PARQUET_URL = (
    "https://huggingface.co/api/datasets/princeton-nlp/SWE-bench_Verified/parquet/default/test"
)
# deterministic chain-link page (HF datasets server resolves to parquet files)


def fetch_swe_bench_verified(
    landing_root: Path,
    *,
    client: httpx.Client | None = None,
    limit: int | None = None,
    source_id: str = "swe-bench-verified",
    batch_id: str = "v1",
) -> dict:
    """Fetch the verified parquet metadata; land raw bytes + a thin item digest list.

    Returns a manifest dict; writes the parquet bytes + a normalized items list
    of {instance_id, repo, base_commit, problem_statement, patch, test_patch,
    FAIL_TO_PASS, PASS_TO_PASS} per record. limit is for smoke runs.
    """
    client = client or httpx.Client(timeout=120.0, follow_redirects=True)
    batch_dir = Path(landing_root) / source_id / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    # 1. list parquet files from the HF datasets-server API
    r = client.get(HF_PARQUET_URL)
    r.raise_for_status()
    files = r.json()
    if files and isinstance(files[0], dict):
        parquet_urls = [f["url"] for f in files]  # datasets-server object form
    else:
        parquet_urls = list(files or [])  # plain URL-string form

    raw_dir = batch_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    landed: list[Path] = []
    for u in parquet_urls:
        name = u.split("/")[-1]
        dest = raw_dir / name
        if not dest.exists():
            rr = client.get(u)
            rr.raise_for_status()
            dest.write_bytes(rr.content)
        landed.append(dest)

    # 2. normalize to digest records (we don't parse parquet with pandas — duckdb)
    items_path = batch_dir / "items.json"
    import duckdb

    records = []
    for p in landed:
        out = duckdb.sql(
            f"""
            select instance_id, repo, base_commit, problem_statement, patch, test_patch,
                   FAIL_TO_PASS, PASS_TO_PASS
            from read_parquet('{p}')
        """
        ).fetchall()
        cols = ["instance_id", "repo", "base_commit", "problem_statement", "patch", "test_patch", "FAIL_TO_PASS", "PASS_TO_PASS"]
        for row in out:
            rec = dict(zip(cols, row, strict=False))
            rec["FAIL_TO_PASS"] = json.loads(rec["FAIL_TO_PASS"]) if isinstance(rec["FAIL_TO_PASS"], str) else rec["FAIL_TO_PASS"]
            records.append(rec)
    if limit:
        records = records[:limit]

    items_path.write_text(json.dumps(records, indent=1))
    manifest = {
        "landing_manifest_version": 1,
        "origin": "public-corpora",
        "source_id": source_id,
        "batch_id": batch_id,
        "deposited": [
            {"path": str(p.relative_to(batch_dir)), "sha256": sha256(p.read_bytes()).hexdigest()}
            for p in landed
        ] + [{"path": "items.json", "sha256": sha256(items_path.read_bytes()).hexdigest()}],
        "item_count": len(records),
        "fetched_urls": parquet_urls,
    }
    (batch_dir / ".landing-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
