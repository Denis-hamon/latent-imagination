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


def test_duckdb_round_trip_queryable_on_a_real_file(tmp_path):
    """File-backed path (what deployers use), queried read-only after close."""
    import duckdb

    records, _ = load_log(_log(tmp_path))
    db = tmp_path / "tel.duckdb"
    result = to_duckdb(records, db)
    assert result["inserted"] == 3 and result["degraded_cells"] == 0
    con = duckdb.connect(str(db), read_only=True)
    try:
        assert con.execute("select count(*) from gate_events").fetchone()[0] == 3
        assert abs(con.execute("select avg(flip_probability) from gate_events").fetchone()[0] - 0.4) < 1e-12
    finally:
        con.close()


def test_reload_over_a_file_db_never_loses_prior_data_on_garbage(tmp_path):
    import duckdb

    records, _ = load_log(_log(tmp_path))
    db = tmp_path / "tel.duckdb"
    to_duckdb(records, db)
    # now poison the log: a payload that's not a dict
    p = tmp_path / "decisions.jsonl"
    p.write_text(p.read_text() + json.dumps({"kind": "gate_annotated", "payload": "oops"}) + "\n")
    records2, _stats = load_log(p)
    assert _stats["malformed_lines"] == 0  # valid JSON with poisoned payload loads (shape degrade counted downstream)
    result = to_duckdb(records2, db)  # must NOT crash; poisoned row counted/degraded
    assert result["inserted"] == 4 and result["degraded_cells"] == 1  # the poisoned payload is counted
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select count(*) from gate_events").fetchone()[0] == 4
    con.close()
