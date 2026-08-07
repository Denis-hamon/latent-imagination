# Public demo #2 — gate advisory through the MCP wire, on gpt-4o trajectories (story 8.4)

**Re-run:** `uv run python demo/gate-mcp/run_demo.py --items 5`
(`--record-dir <scratch>` for re-runs that must not touch the committed record; the
trajectory parquet comes from the node, landing is scratch)

**Fixture honesty (up front, like demo #1):** `demo/gate-advisory/fixtures/predictor.json`
is zero-weight BY CONSTRUCTION (sigmoid(−0.4) ≈ 0.40 on every item — fixture, disclosed
in every annotation via `predictor_disclosure.note`). Nothing here is a trained model.

**Distinctness (FR-25):** harness — Claude Code PreToolUse hooks (demo #1) vs MCP
`tools/call` JSON-RPC (here); vendor — demo #1 played HUMAN gold patches (SWE-bench
Verified) while this one replays REAL gpt-4o-2024-08-06 trajectories (node-side Act I
parquet, hash-pinned in the record). Different harness AND different vendor axis.

**Playback honesty:** patches replayed from the record — 5 of 5 played attempts carry
`resolved=False` (the record's `items[].resolved`, verbatim from the parquet). OQ-10
tier-2 designations are recorded per item (`items[].f2p_designated` from the tasks
parquet; empty when the task has none anchored — an honest empty list, not a placeholder).
Wire notifications follow JSON-RPC law (no id → no reply).

**Bit-rot policy:** identical to demo #1, enforced by `tests/e2e/test_demo_gate_advisory.py`
(scratch re-run via `--record-dir`; committed record never drama-drifted by a test run).
