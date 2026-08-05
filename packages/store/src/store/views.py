"""Convenience DuckDB views over the canonical store.

AD-8: these are convenience, NEVER obligation. They read exactly the paths
documented in store-layout-v1/README.md; a stranger with raw duckdb can always
reproduce the same queries by hand.
"""

from __future__ import annotations

from pathlib import Path


def canonical_snapshots_sql(store_root: Path | str) -> str:
    """SQL string for the 'all canonical snapshots' view — convenience only."""
    root = Path(store_root)
    return f"""
        select *
        from read_parquet('{root}/canonical/snapshots/*/*.parquet', union_by_name = true)
    """.strip()
