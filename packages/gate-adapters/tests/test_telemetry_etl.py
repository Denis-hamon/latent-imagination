"""Deployer telemetry ETL (story 5.6) — load, columnarize, query, all local."""

from __future__ import annotations

import json

import pytest
from core_schema.errors import SchemaError
from gate_adapters.telemetry_etl import load_log, to_duckdb

LINE = {
    "schema_version": 1, "kind": "gate_annotated", "occurred_at": "2026-08-06T10:00:00Z",
    "payload": {"candidate": {"repo": "o/r", "patch_sha256": "a" * 64,
                              "wire_payload_sha256": "b" * 64},
                "flip_probability": 0.4, "latency_s": 0.005, "corpus_version": "corpus-v0",
                "prediction_target_tier": "user_designated",
                "predictor_disclosure": {"measured_precision": 0.6271}},
}


def _log(tmp_path, n=3, corrupt=0):
    p = tmp_path / "decisions.jsonl"
    p.write_text("\n".join([json.dumps(LINE)] * n + ["{torn"] * corrupt) + "\n")
    return p


def test_load_counts_malformed_without_dying(tmp_path):
    records, stats = load_log(_log(tmp_path, n=3, corrupt=2))
    assert len(records) == 3 and stats["malformed_lines"] == 2


def test_empty_is_coded(tmp_path):
    with pytest.raises(SchemaError) as ei:
        load_log(tmp_path / "decisions.jsonl")
    assert ei.value.code == "LI-GADPT-004"


def test_duckdb_round_trip_queryable(tmp_path):
    records, _ = load_log(_log(tmp_path))
    con = to_duckdb(records, ":memory:")
    n = con.execute("select count(*) from gate_events").fetchone()[0]
    assert n == 3
    p = con.execute("select avg(flip_probability) from gate_events").fetchone()[0]
    assert abs(p - 0.4) < 1e-12
    kinds = con.execute("select distinct kind from gate_events").fetchall()
    assert kinds == [("gate_annotated",)]
