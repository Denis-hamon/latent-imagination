# OQ-3 closure — gate latency budget CLOSED 2026-08-06 (story 5.4)

**Registered budget: p95 ≤ 1.0 s** (`latency-budget-v1.toml` — the PRD §12 placeholder
value, ratified as the budget because measurement landed ≫ 150× under it).

## Measured distribution (serve path; ≈2 000 warm + 60 cold predictions)

Sources of record (committed measurement files — not transcript):
`measurements/latency-2026-08-06-local.json` and `…-node.json`. They carry
`predictor_hash` + `corpus_version` + the workload descriptor.

| Hardware | warm p50 | warm p95 | cold p95 | serve overhead p95 | verdict |
| --- | --- | --- | --- | --- | --- |
| OVH node host CPU (Ubuntu 26.04) | 4.3 ms | **5.1 ms** | 5.1 ms | 0.12 ms | meets-budget |
| Consumer laptop (Apple silicon) | 4.3 ms | **5.5 ms** | 5.3 ms | 0.61 ms | meets-budget |

Harness: `scripts/gate/run_bench.py --hardware … --out governance/gate/measurements/…`
over `packages/gate/src/gate/bench.py`. The published table covers the SERVE PATH —
predictor score AND its overhead (annotate + log) are reported as separate columns
(CR 5.4); workload = embedded deterministic 322-byte patch-like seed (≤ ~25 KB/doc,
disclosed); nearest-rank percentiles.

**Posture honesty (SM-C3):** measured with a structurally-valid `probe-predictor-v0`
artifact whose trained weights are not yet re-exported from an Epic-3 run — latency is
workload-shaped (tokenize + hash + dot over a sparse vector); weights are scalars and
do not change the FLOP count. The GPU is NOT involved (CPU stdlib predictor); NFR-P1's
"single-node GPU box" is satisfied by the node HOST CPU.

**Re-measure duty:** any serve-path change re-runs the bench into a NEW dated file and
updates this table. A warm-p95 OR cold-max breach emits `annotations-async` guidance —
never a claim beyond measurement.
