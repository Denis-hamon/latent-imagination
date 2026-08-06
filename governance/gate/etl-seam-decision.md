# ETL seam decision (story 5.6, AD-10) — RESOLVED 2026-08-06

**Decision: the direct SDK→file writer** (`gate_adapters/telemetry_etl.py` reads the
deployer's `decisions.jsonl` into DuckDB; DuckDB→parquet export is one COPY command
away for anyone who wants columnar).

**Rejected: the OTel file exporter (alpha).** AD-10 allows alpha components only
behind a replaceable seam — and prescribes exactly this alternative ("direct SDK→parquet
writing is the drop-in alternative", architecture spine AD-10). The direct writer IS
that alternative and carries zero alpha risk; the seam stays replaceable: the LIVE-WRITE seam is `gate.decision_log.append_decision`
(one function, one surface in `serve.py`) — an OTel emitter would sit behind THAT contract;
`telemetry_etl` is a READER and is not the seam (CR 5.6 correction).

Phoenix path: the deployer's own Phoenix instance ingests the SAME jsonl/parquet files
(read-only mirror does not own canonical state — spine §structural).
