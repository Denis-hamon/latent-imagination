"""Deployer telemetry ETL sample (story 5.6): the deployer's OWN decisions log
queried with their OWN tools — DuckDB over decisions.jsonl, entirely local
(FR-2 zero custody).

Seam decision (recorded in governance/gate/etl-seam-decision.md): DIRECT
SDK→file writer (no OTel alpha dependency on the deployer path; AD-10's
replaceable seam = this module).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
from core_schema.errors import SchemaError


def load_log(log_path: Path) -> tuple[list[dict], dict]:
    p = Path(log_path)
    if not p.is_file():
        raise SchemaError("LI-GADPT-004", "decisions log missing", {"path": str(p)})
    records: list[dict] = []
    malformed = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            malformed += 1  # torn/foreign lines counted, never fatal
            continue
        if not isinstance(obj, dict) or "kind" not in obj:
            malformed += 1
            continue
        records.append(obj)
    if not records and not malformed:
        raise SchemaError("LI-GADPT-004", "decisions log is empty", {"path": str(p)})
    return records, {"malformed_lines": malformed, "rows": len(records)}


def to_duckdb(records: list[dict], db_path: Path):
    con = duckdb.connect(str(db_path))
    con.execute("DROP TABLE IF EXISTS gate_events")
    con.execute(
        """CREATE TABLE gate_events(
            kind VARCHAR, occurred_at VARCHAR, repo VARCHAR,
            flip_probability DOUBLE, latency_s DOUBLE,
            corpus_version VARCHAR, patch_sha256 VARCHAR,
            wire_payload_sha256 VARCHAR, raw VARCHAR)"""
    )
    for r in records:
        p = r.get("payload") or {}
        cand = p.get("candidate") or {}
        con.execute(
            "INSERT INTO gate_events VALUES (?,?,?,?,?,?,?,?,?)",
            [r.get("kind"), r.get("occurred_at"), cand.get("repo"),
             p.get("flip_probability"), p.get("latency_s"),
             p.get("corpus_version"), cand.get("patch_sha256"),
             cand.get("wire_payload_sha256"), json.dumps(r, sort_keys=True)],
        )
    return con


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
    con = to_duckdb(records, args.db)
    print(json.dumps({"loaded": stats}, indent=2))
    for name, q in SAMPLE_QUERIES.items():
        print(f"--- {name}")
        for row in con.execute(q).fetchall():
            print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
