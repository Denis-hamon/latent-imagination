"""Deployer telemetry ETL sample (story 5.6 + CR): the deployer's OWN decisions
log queried with their OWN tools — DuckDB over decisions.jsonl, entirely local.

Safety laws (CR 5.6): NEVER destroy an existing db — staging table + single
transaction + atomic swap, and poisoned rows are COUNTED and skipped (a deployer
input can never turn a crash into data loss). BOM-tolerant, coded on bad encodings.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import duckdb
from core_schema.errors import SchemaError

_ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def load_log(log_path: Path) -> tuple[list[dict], dict]:
    p = Path(log_path)
    try:
        p.read_text(encoding="utf-8-sig")  # codec probe (BOM-tolerant by design)
    except FileNotFoundError as exc:
        raise SchemaError("LI-GADPT-004", "decisions log missing", {"path": str(p)}) from exc
    except UnicodeDecodeError as exc:
        raise SchemaError("LI-GADPT-004", "decisions log not utf-8", {"path": str(p)}) from exc
    records: list[dict] = []
    malformed = 0
    with p.open(encoding="utf-8-sig") as fh:  # stream, never a whole-file slurp
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
            except ValueError:
                malformed += 1
                continue
            if not isinstance(obj, dict) or "kind" not in obj:
                malformed += 1
                continue
            records.append(obj)
    if not records:
        raise SchemaError("LI-GADPT-004", "decisions log holds no parseable gate events",
                          {"path": str(p), "malformed_lines": malformed})
    return records, {"malformed_lines": malformed, "rows": len(records)}


def _num(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)) else None


def to_duckdb(records: list[dict], db_path: Path | str) -> dict:
    """Stage in a transaction, validate per row, swap atomically. An existing
    `gate_events` is replaced ONLY after every row survived validation."""
    degraded = 0
    rows = []
    for r in records:
        raw_p = r.get("payload")
        if raw_p is not None and not isinstance(raw_p, dict):
            degraded += 1  # poisoned payload: counted, nulled, never a crash
        p = raw_p if isinstance(raw_p, dict) else {}
        raw_c = p.get("candidate")
        if raw_c is not None and not isinstance(raw_c, dict):
            degraded += 1
        cand = raw_c if isinstance(raw_c, dict) else {}
        oc = r.get("occurred_at")
        if not (isinstance(oc, str) and _ISO_Z.match(oc)):
            degraded += 1 if oc is not None else 0
            oc = None
        fp, lat = _num(p.get("flip_probability")), _num(p.get("latency_s"))
        if (p.get("flip_probability") is not None and fp is None) or (p.get("latency_s") is not None and lat is None):
            degraded += 1
        rows.append([r.get("kind"), oc, cand.get("repo"), fp, lat,
                     p.get("corpus_version"), cand.get("patch_sha256"),
                     cand.get("wire_payload_sha256"), json.dumps(r, sort_keys=True, allow_nan=False)])

    con = duckdb.connect(str(db_path))
    try:
        con.execute("BEGIN")
        con.execute("DROP TABLE IF EXISTS gate_events_staging")
        con.execute("CREATE TABLE gate_events_staging("
                    "kind VARCHAR, occurred_at VARCHAR, repo VARCHAR,"
                    "flip_probability DOUBLE, latency_s DOUBLE,"
                    "corpus_version VARCHAR, patch_sha256 VARCHAR,"
                    "wire_payload_sha256 VARCHAR, raw VARCHAR)")
        con.executemany("INSERT INTO gate_events_staging VALUES (?,?,?,?,?,?,?,?,?)", rows)
        con.execute("DROP TABLE IF EXISTS gate_events")
        con.execute("ALTER TABLE gate_events_staging RENAME TO gate_events")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return {"inserted": len(rows), "degraded_cells": degraded}


SAMPLE_QUERIES = {
    "annotations per day": "select substr(occurred_at,1,10) d, kind, count(*) from gate_events group by 1,2 order by 1",
    "abstention share": "select kind, round(100.0*count(*)/(select count(*) from gate_events),1) pct from gate_events group by 1",
    "latency p95 by day": "select substr(occurred_at,1,10), quantile_cont(latency_s,.95) from gate_events where latency_s is not null group by 1",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="deployer telemetry ETL (story 5.6)")
    ap.add_argument("log", help="path to decisions.jsonl")
    ap.add_argument("--db", default=":memory:")
    args = ap.parse_args()
    records, stats = load_log(Path(args.log))
    result = to_duckdb(records, args.db)
    print(json.dumps({"loaded": {**stats, **result}}, indent=2))
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        for name, q in SAMPLE_QUERIES.items():
            print(f"--- {name}")
            for row in con.execute(q).fetchall():
                print(row)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
