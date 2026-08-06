# OQ-3 closure — gate latency budget CLOSED 2026-08-06 (story 5.4)

**Registered budget: p95 ≤ 1.0 s** (`latency-budget-v1.toml` — the PRD §12 placeholder,
ratified because measurement landed ~30× under it).

## Measured distribution (serve path, workload = mixed-size candidate docs, ~2 000 warm preds)

| Hardware (per AD-10 envelope) | p50 | p95 | p99 | cold max | verdict |
| --- | --- | --- | --- | --- | --- |
| OVH node host CPU (Ubuntu 26.04, 2× L40S GPU host) | 7.3 ms | **30.6 ms** | 31.0 ms | 30.1 ms | meets-budget |
| Consumer laptop (Apple silicon) | 7.3 ms | **28.9 ms** | 29.6 ms | 28.7 ms | meets-budget |

Harness: `scripts/gate/run_bench.py` over `packages/gate/src/gate/bench.py`; per-prediction
latency harvested from the annotations themselves (the serve path measures itself; the
decision log is the latency log per 5.2).

**Posture honesty (SM-C3):** measured with a structurally-valid `probe-predictor-v0`
artifact whose trained weights are not yet re-exported from an Epic-3 run — latency is
workload-shaped (tokenize + hash + dot over a sparse vector); weights are scalars and do not
change the FLOP count. The GPU is NOT involved (the predictor is CPU stdlib); the
"single-node GPU box" framing in NFR-P1 is correctly satisfied by the node HOST CPU.

**Re-measure duty:** any change to the serve path (featurization, scorer, artifact width)
re-runs the bench and re-publishes this table. A miss emits `annotations-async` guidance,
never a claim beyond measurement.
