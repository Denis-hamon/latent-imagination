"""Public demo #1 (story 5.5): scripted, re-runnable, on REAL tasks.

Takes real SWE-bench Verified items from the local landing parquet, plays the
gold patches through the claude-code hook adapter (the documented PreToolUse
wire shape — the vendor loop itself is the deployer's pilot step), and captures
the annotation-visible record: console transcript + decisions.jsonl.

Bit-rot policy (FR-25/§9): this demo is a TIME-STAMPED artifact — it pins its
inputs (parquet sha256), its predictor pin, and its date. If any input rots,
re-run from sources; nothing here pretends to be evergreen.

Usage: uv run python demo/gate-advisory/run_demo.py [--items 5]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path

import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = Path(__file__).resolve().parent
LANDING = REPO / "data" / "landing"
PREDICTOR_ART = DEMO_DIR / "fixtures" / "predictor.json"  # committed, small, structurally valid


def _real_items(parquet: Path, n: int) -> list[dict]:
    rows = pq.read_table(parquet).to_pylist()[:n]
    out = []
    for r in rows:
        out.append({
            "instance_id": r["instance_id"],
            "repo": r.get("repo", "unknown/unknown"),
            "gold_patch": r.get("patch") or "",
        })
    return out


def _as_hook_payload(item: dict) -> str:
    """The documented PreToolUse wire shape: Claude Code writes the fixed file —
    the file_path is the patch's real first target (what the vendor emits)."""
    import re

    patch = item["gold_patch"][:4000]
    m = re.search(r"^\+\+\+ b/(.+)$", patch, re.MULTILINE)
    target = m.group(1) if m else "src/fix.py"
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": target, "content": patch, "repo": item["repo"]},
    })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=int, default=5)
    args = ap.parse_args()

    from gate.serve import GateServer
    from gate_adapters.claude_code_hooks import run_hook

    parquet = LANDING / "swe-bench-verified" / "v1" / "raw" / "0.parquet"
    if not parquet.exists():
        raise SystemExit("landing parquet missing (scp from the node; landing is scratch)")

    snap = DEMO_DIR / "fixtures"
    phash = sha256(PREDICTOR_ART.read_bytes()).hexdigest()
    out_dir = DEMO_DIR / "record"
    out_dir.mkdir(parents=True, exist_ok=True)
    server = GateServer.load(snap, expected_predictor_hash=phash,
                             log_path=out_dir / "decisions.jsonl",
                             # OQ-10 tier 2: the deployer designates each task's own
                             # F2P tests as the prediction target (SWE-bench pilot
                             # posture — what a Kenji on this task class configures).
                             user_test_selection="task-f2p-tests")

    transcript = StringIO()
    items = _real_items(parquet, args.items)
    with redirect_stdout(transcript):
        for it in items:
            print(f"=== demo task: {it['instance_id']} ({it['repo']}) ===")
            run_hook(_as_hook_payload(it), server)

    cap = {
        "demo": "gate-advisory-public-demo-1",
        "demo_recorded_on": subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
                                           capture_output=True, text=True, check=False).stdout.strip(),
        "input_parquet_sha256": sha256(parquet.read_bytes()).hexdigest(),
        "predictor_pin_sha256": phash,
        "items_played": len(items),
        "transcript": transcript.getvalue(),
    }
    (out_dir / "demo-record.json").write_text(json.dumps(cap, indent=2) + "\n")
    print(transcript.getvalue())
    print(f"[record] {out_dir}/demo-record.json + decisions.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
