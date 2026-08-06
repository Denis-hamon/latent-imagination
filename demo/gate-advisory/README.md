# Public demo #1 — advisory gate on real SWE-bench tasks (story 5.5)

**Re-run:** `uv run python demo/gate-advisory/run_demo.py --items 5`
(needs `data/landing/swe-bench-verified/v1/raw/0.parquet` — scp from the node; landing is scratch).

**What it evidences (CAP-5 setup 1):** a scripted, re-runnable run on REAL tasks
(SWE-bench Verified): each candidate patch crosses the documented PreToolUse wire,
the advisory appears BEFORE any execution would happen, carrying the flip
probability + rationale pointer — in BOTH channels (user `systemMessage`, agent
`additionalContext`) — and every decision lands in the deployer-local
Trace-Schema log (`record/decisions.jsonl`). The vendor loop itself (Claude Code
with the hook registered) is the deployer's pilot step; the wire shape here is
reproduced from the documented contract, on purpose (NFR-V1, zero vendor
cooperation).

**Disclosures (honesty block):**
- `fixtures/predictor.json` is STRUCTURALLY valid with zero weights — the demo
  scores the workload, not a trained model; every flip probability is
  sigmoid(−0.4) ≈ 0.40 by fixture construction. The disclosure line in each
  annotation (measured precision 0.6271, sub-bar, branch iii) is the REAL
  Epic-3 measurement, quoted from the sealed envelope.
- OQ-10 policy on show: `user_designated` tier (SWE task F2P designated);
  without it, the same run abstains with a recorded `prediction_refused`.

**Bit-rot policy (FR-25/§9):** this demo is a TIME-STAMPED artifact
(2026-08-06): it pins its input parquet sha256, its predictor pin, and its date
in `record/demo-record.json`. If any input rots, re-run from sources; nothing
here pretends to be evergreen.

**First in-the-wild Trace-Schema consumption:** the decisions log IS the
telemetry surface a deployer inspects with their own tools (story 5.6's ETL
sample reads exactly this file, on their premises, with zero custody).
