"""Public demo #2 (story 8.4, FR-25): a SECOND distinct setup — MCP gateway
wire on a DIFFERENT model vendor (openai: gpt-4o-2024-08-06 real trajectories).

Re-run: uv run python demo/gate-mcp/run_demo.py [--items 5]
Needs: data/landing/swe-smith-trajectories/smith-matched-full/raw/ticks-00000.parquet
(node parity landing).

Disclosure gate: we PLAY BACK recorded trajectories (FR-25's replay evidence);
the advisory fires pre-execution relative to each replayed attempt; the demo
pins the trajectory parquet hash + the predictor fixture pin + the wire
contract version. Same bit-rot policy as demo #1.
"""

from __future__ import annotations

import argparse
import json
from contextlib import redirect_stdout
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO
from pathlib import Path

import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = Path(__file__).resolve().parent
LANDING = REPO / "data" / "landing"
PARQUET = LANDING / "swe-smith-trajectories" / "smith-matched-full" / "raw" / "ticks-00000.parquet"
FIXTURES = REPO / "demo" / "gate-advisory" / "fixtures"  # same pinned artifact (recorded)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=int, default=5)
    ap.add_argument("--model", default="gpt-4o-2024-08-06")
    args = ap.parse_args()

    from gate.serve import GateServer
    from gate_adapters.mcp_gateway import run_mcp_message

    if not PARQUET.is_file():
        raise SystemExit("landing parquet missing (scp from the node; landing is scratch)")
    rows = [r for r in pq.read_table(PARQUET).to_pylist() if r["model"] == args.model and r["patch"]]
    rows = rows[: args.items]
    if not rows:
        raise SystemExit(f"no trajectories for model {args.model}")

    snap, phash = FIXTURES, sha256((FIXTURES / "predictor.json").read_bytes()).hexdigest()
    out_dir = DEMO_DIR / "record"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decisions.jsonl").unlink(missing_ok=True)
    server = GateServer.load(snap, expected_predictor_hash=phash,
                             log_path=out_dir / "decisions.jsonl",
                             user_test_selection="the task's FAIL_TO_PASS list")

    transcript = StringIO()
    with redirect_stdout(transcript):
        for i, row in enumerate(rows):
            msg = json.dumps({
                "jsonrpc": "2.0", "id": i, "method": "tools/call",
                "params": {"name": "apply_patch",
                           "arguments": {"path": "src/fix.py", "content": row["patch"]}},
            })
            print(f"=== demo task: {row['instance_id']} (model {row['model']}, resolved={row['resolved']}) ===")
            out = run_mcp_message(msg, server)
            print(json.dumps(out, indent=1))

    cap = {
        "demo": "gate-mcp-public-demo-2",
        "recorded_on": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "wire_contract": "MCP tools/call JSON-RPC 2.0 (documented protocol surface)",
        "trajectory_input_sha256": sha256(PARQUET.read_bytes()).hexdigest(),
        "predictor_pin_sha256": phash,
        "model_family": args.model,
        "items_played": len(rows),
        "resolved_outcomes_played": [bool(r["resolved"]) for r in rows],
        "transcript": transcript.getvalue(),
    }
    (out_dir / "demo-record.json").write_text(json.dumps(cap, indent=2) + "\n")
    print(transcript.getvalue())
    print(f"[record] {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
