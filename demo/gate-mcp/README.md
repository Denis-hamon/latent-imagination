# Public demo #2 — gate advisory through the MCP wire, on a DIFFERENT vendor (story 8.4)

**Re-run:** `uv run python demo/gate-mcp/run_demo.py --items 5`
(needs `data/landing/swe-smith-trajectories/smith-matched-full/raw/ticks-00000.parquet` — scp from the node; landing is scratch)

**What it evidences (FR-25, second distinct setup):** same gate doctrine, a DIFFERENT
interception harness (MCP `tools/call` JSON-RPC — a vendor-documented protocol surface)
on trajectories from a DIFFERENT model vendor (openai `gpt-4o-2024-08-06`, from the Act I
field measurement record). Paired with demo #1 (`demo/gate-advisory/`: Claude Code hooks +
Anthropic-class trajectories) the two demos satisfy NFR-V1 (documented surfaces) × FR-25
(different harness AND different vendor cages).

**Playback honesty:** we replay recorded trajectory patches (the real false starts —
4 of 5 played attempts carry `resolved=False` on the wire's disclosure); NO claim that the
model was re-run. The F2P designation rides OQ-10's tier-2 (user-designated) because
replay patches don't touch test files; abstention posture remains what 5.3/8.2 tests prove.

**Bit-rot policy:** identical to demo #1 (timestamped artifact; re-run from sources;
pins in `record/demo-record.json`).
