"""Run the gate latency bench (story 5.4). Workload: mixed-size candidate docs.
Disclosure: measured with a structurally-valid probe-predictor-v0 artifact
(zero weights — latency is workload-shaped: hashing + dot; weights are scalars,
they do not change the FLOP count)."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "act1"))

from gate.bench import bench_report, load_budget, verdict
from gate.intercept import CandidateCtx
from gate.serve import GateServer


def _bench_artifact(tmp: Path) -> tuple[Path, str]:
    from hashlib import sha256

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


def workload(seed_file: Path, n: int = 60) -> list[str]:
    base = seed_file.read_text() if seed_file.exists() else "fix: bug in parser\n"
    rng = random.Random(2026)
    docs = []
    for i in range(n):
        scale = rng.choice([1, 4, 20, 80])  # tiny → ~300 KB real-patch-like sizes
        docs.append(base * scale + f"\n# FAILED TESTS\ntests/test_gen_{i % 7}.py::t_{i}\n")
    return docs


def main() -> int:
    import tempfile

    hardware = sys.argv[1] if len(sys.argv) > 1 else "unspecified-host"
    with tempfile.TemporaryDirectory() as td:
        snap, phash = _bench_artifact(Path(td) / "snap")
        server = GateServer.load(snap, expected_predictor_hash=phash,
                                 log_path=Path(td) / "dep" / "decisions.jsonl")
        docs = workload(Path(__file__).resolve().parents[2] / "README.md")
        rep = bench_report(server, docs, lambda d: CandidateCtx(
            repo="o/r", patch_diff=d, rationale_ptr="x"), hardware_note=hardware)
        budget = load_budget(Path("governance/gate/latency-budget-v1.toml"))
        out = {"report": rep, "verdict": verdict(rep, budget)}
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
