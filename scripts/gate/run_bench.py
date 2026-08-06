"""Run the gate latency bench (story 5.4). Workload = embedded deterministic
seed (byte-size truth-in-advertising); measurement persists with --out for the
committed record (the node number must be a FILE, not transcript)."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from gate.bench import bench_report, load_budget, verdict
from gate.intercept import CandidateCtx
from gate.serve import GateServer

REPO = Path(__file__).resolve().parents[2]

# 322-byte patch-like seed; scale 80× tops at ~25 KB per doc (disclosed size).
_SEED = """diff --git a/pkg/parser.py b/pkg/parser.py
--- a/pkg/parser.py
+++ b/pkg/parser.py
@@ -88,7 +88,9 @@ def parse(stream):
-    return Node(head(stream))
+    if not stream:
+        raise ValueError("empty stream")
+    return Node(head(stream), tail=stream[1:])
FAILED TESTS
tests/test_parser.py::test_empty_stream
"""


def _bench_artifact(tmp: Path) -> tuple[Path, str]:
    tmp.mkdir(parents=True, exist_ok=True)
    art = {
        "predictor_version": "probe-predictor-v0", "corpus_version": "corpus-v0",
        "measured": {"precision": 0.6271},
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "n_features": 2**12,
                       "alternate_sign": False, "norm": "l2", "lowercase": True,
                       "token_pattern": r"\b\w\w+\b"},
        "model": {"kind": "logreg-sigmoid", "intercept": 0.5, "coefficients": [0.0] * 2**12},
    }
    (tmp / "META.json").write_text(json.dumps({"layout_version": "store-layout-v1",
                                               "store_version": "a" * 64}))
    blob = json.dumps(art, allow_nan=False)
    (tmp / "predictor.json").write_text(blob)
    return tmp, sha256(blob.encode()).hexdigest()


def workload(n: int = 60) -> list[str]:
    import random

    rng = random.Random(2026)
    return [_SEED * rng.choice([1, 4, 20, 80]) + f"\ntests/test_gen_{i % 7}.py::t_{i}\n"
            for i in range(n)]


def main() -> int:
    import tempfile

    ap = argparse.ArgumentParser(description="gate latency bench (story 5.4)")
    ap.add_argument("--hardware", required=True)
    ap.add_argument("--out", default=None, help="persist the measurement JSON (committed record)")
    args = ap.parse_args()
    budget = load_budget(REPO / "governance" / "gate" / "latency-budget-v1.toml")  # FIRST
    with tempfile.TemporaryDirectory() as td:
        snap, phash = _bench_artifact(Path(td) / "snap")
        server = GateServer.load(snap, expected_predictor_hash=phash,
                                 log_path=Path(td) / "dep" / "decisions.jsonl")
        rep = bench_report(server, workload(), lambda d: CandidateCtx(
            repo="o/r", patch_diff=d, rationale_ptr="x"), hardware_note=args.hardware)
        out = {
            "measured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "report": rep,
            "verdict": verdict(rep, budget),
        }
        blob = json.dumps(out, indent=2)
        print(blob)
        if args.out:
            p = REPO / args.out if not Path(args.out).is_absolute() else Path(args.out)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(blob + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
