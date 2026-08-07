# FR-25 closure — distinctness checklist (registered 2026-08-06)

PRD FR-25: the gate demonstrated from ≥2 DISTINCT agent setups (different harness
AND different model vendor).

| Axis | Demo #1 (`demo/gate-advisory/`) | Demo #2 (`demo/gate-mcp/`) |
|---|---|---|
| Interception surface | Claude Code **PreToolUse** hooks (documented) | **MCP `tools/call`** JSON-RPC 2.0, pinned at spec revision 2025-06-18 (documented) |
| Vendor axis of the played data | human gold patches (SWE-bench Verified — the task-reference data; vendor-neutral by nature) | REAL model trajectories from `gpt-4o-2024-08-06` (openai) — Act I mesh parquet, hash-pinned in the record |
| Advisory posture | zero-weight fixture + sub-bar disclosure (measured 0.6271 quoted) | same fixture + same disclosure, recorded verbatim per annotation |
| Record hygiene | sanitized, counts published, tripwires | sanitized, counts published, `--record-dir` scratch + tripwires |

**Explicitly NOT claimed:** no live vendor CLI/LLM was executed for either demo (the
wire is the documented contract, played back with real recorded data); the ranking
TOOL's second-setup demonstration is deferred to the pilot window with its own record
(this closure covers the GATE advisory leg, registered honestly).

**Evidence:** `demo/gate-advisory/demo-record.json` + `demo/gate-mcp/record/demo-record.json`
both carry input sha256 + predictor pin + wire pin + timestamps; both artifacts are
re-runnable from the repo (node landing pulls documented).
