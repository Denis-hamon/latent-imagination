# Gate telemetry — first in-the-wild Trace-Schema consumption (stories 5.3–5.6)

**Surface:** the deployer-local `decisions.jsonl` (fenced: never inside a store root,
one `os.write` per line under flock, utf-8). Event kinds: `gate_annotated`,
`prediction_refused` — both StoreEvents (Trace Schema, `schema_version: 1`).

**Demo #1 (2026-08-06, `demo/gate-advisory/`) is the first in-the-wild consumption**:
five real SWE-bench items crossed the documented PreToolUse wire; the deployer's
inspection path (story 5.6's ETL sample) reads exactly this file, on their premises,
zero custody. The committed record is sanitized with the frozen patterns
(`governance/sanitize-policy.toml`) and carries its `sanitize_counts` — proven clean.

**Lineage keys an auditor gets per event:**
- `candidate.patch_sha256` — hash of what the SCORER saw (adapter reconstruction);
- `candidate.wire_payload_sha256` — hash of what the WIRE bore;
- dataset link = the demo record's per-item `gold_patch_sha256`;
- `predictor_disclosure` — the pinned manifest's measured block, verbatim (incl.
  fixture notes — a demo artifact never dresses up as a trained one).

**Mixed producers (story 8.2):** the log also carries `candidates_ranked` (ranking
tool) — analytics queries filter per kind (`where kind = 'gate_annotated'` for the
flip/latency distributions; ranking rows carry no flip_probability).

**Bit-rot policy:** demo = time-stamped artifact; re-running regenerates the record
(wall-clock fields vary by design); tripwire = `tests/e2e/test_demo_gate_advisory.py`
(skip-gated when the landing parquet is absent).
