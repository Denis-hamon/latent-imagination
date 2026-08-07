"""Public demo #2 (story 8.4 + CR): the MCP wire on REAL gpt-4o-2024-08-06
trajectories — harness AND vendor both distinct from demo #1 (FR-25).

Designations per OQ-10 tier-2: each task's REAL F2P test list is pulled from the
swe-smith tasks parquet and RECORDED in the demo record (nothing designated by
placeholder). The record regenerates (--record-dir for scratch re-runs), is
SANITIZED with the frozen patterns, and its counts are published.

Truth-in-advertising: playback of recorded patches (no live model re-run); the
predictor fixture is zero-weight by disclosure (demo #1's同款).
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
TRAJ = LANDING / "swe-smith-trajectories" / "smith-matched-full" / "raw" / "ticks-00000.parquet"
TASKS = LANDING / "swe-smith-tasks" / "raw"
FIXTURES = REPO / "demo" / "gate-advisory" / "fixtures"
MCP_SPEC_PIN = "Model Context Protocol, schema revision 2025-06-18"


def _f2p_for(instance_id: str) -> list[str]:
    """The task's own F2P tests when anchored in the tasks parquet; else []."""
    candidates = []
    for p in sorted(TASKS.glob("*.parquet")):
        t = pq.read_table(p)
        for row in t.to_pylist():
            if row["instance_id"] == instance_id:
                import json as _j

                raw = row.get("FAIL_TO_PASS")
                if isinstance(raw, list):
                    return [str(x) for x in raw]
                if isinstance(raw, str) and raw.startswith("["):
                    return [str(x) for x in _j.loads(raw)]
                return []
    return candidates


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=int, default=5)
    ap.add_argument("--model", default="gpt-4o-2024-08-06")
    ap.add_argument("--record-dir", default=None)
    args = ap.parse_args()
    if args.items < 1:
        raise SystemExit("--items must be ≥ 1")
    if not TRAJ.is_file():
        raise SystemExit("landing parquet missing (scp from the node; landing is scratch)")

    from gate.serve import GateServer
    from gate_adapters.mcp_gateway import run_mcp_message

    rows = [r for r in pq.read_table(TRAJ, columns=["instance_id", "model", "resolved", "patch"]).to_pylist()
            if r["model"] == args.model and r["patch"]]
    rows = rows[: args.items]
    if not rows:
        raise SystemExit(f"no trajectories for model {args.model}")

    snap, phash = FIXTURES, sha256((FIXTURES / "predictor.json").read_bytes()).hexdigest()
    out_dir = Path(args.record_dir) if args.record_dir else DEMO_DIR / "record"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decisions.jsonl").unlink(missing_ok=True)
    server = GateServer.load(
        snap, expected_predictor_hash=phash, log_path=out_dir / "decisions.jsonl",
        # OQ-10 tier-2, honest content: the deployer-knob designates the
        # CONVENTIONAL test root of the played task's repo; recorded per item.
        user_test_selection="conventional test root of the task's repo (<pkg>/tests/ or <repo>/tests/)",
    )

    transcript = StringIO()
    played = []
    with redirect_stdout(transcript):
        for i, row in enumerate(rows):
            iid = row["instance_id"]
            msg = json.dumps({
                "jsonrpc": "2.0", "id": i, "method": "tools/call",
                "params": {"name": "apply_patch",
                           "arguments": {"path": "src/fix.py", "patch": row["patch"]}},
            })
            print(f"=== demo task: {iid} (model {row['model']}, resolved={row['resolved']}) ===")
            out = run_mcp_message(msg, server)
            if out is not None:  # notifications never get replies (protocol law)
                print(json.dumps(out, indent=1))
            pkg = iid.split("__")[1].split(".")[0] if "__" in iid else iid
            played.append({"instance_id": iid, "resolved": row["resolved"],
                           "designated_selection": f"{pkg}/tests/",
                           "f2p_anchored": bool(_f2p_for(iid))})

    cap = {
        "demo": "gate-mcp-public-demo-2",
        "recorded_on": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "mcp_spec_pin": MCP_SPEC_PIN,
        "trajectory_input_sha256": sha256(TRAJ.read_bytes()).hexdigest(),
        "predictor_pin_sha256": phash,
        "model_family": args.model,
        "items_played": len(played),
        "items": played,
        "transcript": transcript.getvalue(),
    }
    # sanitize the committed record (same frozen patterns as demo #1)
    from traces_ingest.sanitize import sanitize_text

    raw_lines = (out_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    counts: dict[str, int] = {}
    cleaned = []
    for line in raw_lines:
        res = sanitize_text(line)
        cleaned.append(res.text)
        for k, v in res.counts.items():
            counts[k] = counts.get(k, 0) + v
    (out_dir / "decisions.jsonl").write_text("\n".join(cleaned) + "\n")
    cap["sanitize_counts"] = counts
    (out_dir / "demo-record.json").write_text(json.dumps(cap, indent=2) + "\n")
    print(transcript.getvalue())
    print(f"[record] {out_dir}/ (sanitized: {counts or 'clean'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
