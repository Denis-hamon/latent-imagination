"""Build the Clean Tier from landing parquets (story 4.3 driver).

Thin orchestration only — all logic lives in `packages/corpus` (writer-guard
discipline: this script holds no store-aimed writes, it CALLS the owning stage).

Usage: uv run python scripts/corpus/build_clean_tier.py [--landing data/landing] [--store data/store]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path

from corpus.clean import (
    assemble_clean,
    evaluate_floor,
    iter_smith_candidates,
    iter_swe_bench_candidates,
    load_hardening_policy,
    load_inventory,
)
from corpus.clean_emit import emit_clean_tier


def _sha(p: Path) -> str:
    return sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--landing", default="data/landing")
    ap.add_argument("--store", default="data/store")
    ap.add_argument("--known-hackable", default=None, help="JSON list of instance ids (published lists)")
    args = ap.parse_args()
    root = Path.cwd()
    landing, store = root / args.landing, root / args.store

    smith = sorted((landing / "swe-smith-tasks" / "raw").glob("*.parquet"))
    verified = sorted((landing / "swe-bench-verified" / "v1" / "raw").glob("*.parquet"))
    if not smith and not verified:
        raise SystemExit("no candidate data under landing (scp from the node; landing is scratch)")

    cands = iter_smith_candidates(smith) + iter_swe_bench_candidates(verified)
    source_hashes = {str(p): _sha(p) for p in [*smith, *verified]}
    policy = load_hardening_policy(root / "governance/corpus/hardening-policy-v1.toml")
    inv = load_inventory(root / "governance/corpus/license-inventory-v1.json")
    known = set(json.loads(Path(args.known_hackable).read_text())) if args.known_hackable else None

    out = assemble_clean(cands, inv, policy["allowlist"], known_hackable=known)
    verdict = evaluate_floor(
        len(out["kept"]), policy["band_min"], policy["band_max"],
        sources_exhausted=False,  # SWE-Gym/R2E-Gym declared, not yet fetched (window action)
    )
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    code_commit = head.stdout.strip()
    if head.returncode != 0 or len(code_commit) != 40:
        raise SystemExit("not in a git work tree")
    m = emit_clean_tier(
        store, out["kept"], out["rejects"], out["by_reason"], verdict,
        artifact_version="v0",
        hardening_policy_path=root / "governance/corpus/hardening-policy-v1.toml",
        license_inventory_path=root / "governance/corpus/license-inventory-v1.json",
        candidates_total=len(cands), source_hashes=source_hashes,
        known_hackable_used=known is not None, code_commit=code_commit,
    )
    print(json.dumps({"artifact": f"{m['artifact_id']} {m['artifact_version']}",
                      "kept": len(out["kept"]), "rejected": len(out["rejects"]),
                      "floor_rung": verdict.rung}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
