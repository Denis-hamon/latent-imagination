"""Public demo #1 (story 5.5 + CR): scripted, re-runnable, on REAL tasks.

Real SWE-bench Verified items; gold patches cross the documented PreToolUse
wire shape UNTRUNCATED; the deployer designates each task's REAL FAIL_TO_PASS
list (OQ-10 tier-2). Each run REGENERATES `record/` from scratch — re-running
reproduces the same-SIZED record (wall-clock fields `occurred_at`/`latency_s`
/`demo_recorded_on` vary BY DESIGN and are the only varying fields).

The committed decisions are the SANITIZED copy (frozen governance patterns,
counts published in demo-record.json) — FR-2's hygiene applied to the demo
record itself.
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
PREDICTOR_ART = DEMO_DIR / "fixtures" / "predictor.json"
CLAUDE_CODE_WIRE_PIN = "hooks contract as documented 2026-08-06 (wire reproduced, not vendor-run — see README)"


def _real_items(parquet: Path, n: int) -> list[dict]:
    def _as_list(raw):
        if isinstance(raw, list):
            return [str(t) for t in raw]
        if isinstance(raw, str) and raw.strip().startswith("["):
            return [str(t) for t in json.loads(raw)]
        return []

    rows = pq.read_table(parquet).to_pylist()[:n]
    return [{
        "instance_id": r["instance_id"],
        "repo": r.get("repo", "unknown/unknown"),
        "gold_patch": r.get("patch") or "",
        "f2p": _as_list(r.get("FAIL_TO_PASS")),
    } for r in rows]


def _as_hook_payload(item: dict) -> str:
    """Documented PreToolUse shape; file_path = the patch's first real target,
    content = the FULL gold patch (no silent truncation, CR 5.5)."""
    import re

    m = re.search(r"^\+\+\+ b/(.+)$", item["gold_patch"], re.MULTILINE)
    target = m.group(1) if m else "src/fix.py"
    if "\n" in target or not target:
        target = "src/fix.py"
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": target, "content": item["gold_patch"]},
    })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=int, default=5)
    ap.add_argument("--record-dir", default=None, help="scratch target (CI); default: the committed record/")
    args = ap.parse_args()

    from gate.serve import GateServer
    from gate_adapters.claude_code_hooks import run_hook
    from traces_ingest.sanitize import sanitize_text

    parquet = LANDING / "swe-bench-verified" / "v1" / "raw" / "0.parquet"
    if not parquet.exists():
        raise SystemExit("landing parquet missing (scp from the node; landing is scratch)")

    snap = DEMO_DIR / "fixtures"
    phash = sha256(PREDICTOR_ART.read_bytes()).hexdigest()
    out_dir = Path(args.record_dir) if args.record_dir else DEMO_DIR / "record"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decisions.jsonl").unlink(missing_ok=True)  # regenerate, never falsify

    items = _real_items(parquet, args.items)
    server = GateServer.load(snap, expected_predictor_hash=phash,
                             log_path=out_dir / "decisions.jsonl",
                             user_test_selection="the task's FAIL_TO_PASS list")

    transcript = StringIO()
    with redirect_stdout(transcript):
        for it in items:
            print(f"=== demo task: {it['instance_id']} ({it['repo']}) ===")
            run_hook(_as_hook_payload(it), server)

    # sanitize the committed record (FR-2 habit, on ourselves)
    raw_lines = (out_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    counts: dict[str, int] = {}
    cleaned = []
    for line in raw_lines:
        res = sanitize_text(line)
        cleaned.append(res.text)
        for k, v in res.counts.items():
            counts[k] = counts.get(k, 0) + v
    (out_dir / "decisions.jsonl").write_text("\n".join(cleaned) + "\n")

    cap = {
        "demo": "gate-advisory-public-demo-1",
        "demo_recorded_on": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "vendor_wire_pin": CLAUDE_CODE_WIRE_PIN,
        "input_parquet_sha256": sha256(parquet.read_bytes()).hexdigest(),
        "predictor_pin_sha256": phash,
        "items": [{"instance_id": it["instance_id"], "repo": it["repo"],
                   "f2p_designated": it["f2p"], "gold_patch_sha256": sha256(it["gold_patch"].encode()).hexdigest()}
                  for it in items],
        "sanitize_counts": counts,  # expect {} — proven, not presumed
        "transcript": transcript.getvalue(),
    }
    (out_dir / "demo-record.json").write_text(json.dumps(cap, indent=2) + "\n")
    print(transcript.getvalue())
    print(f"[record] {out_dir}/demo-record.json + decisions.jsonl (sanitized: {counts or 'clean'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
