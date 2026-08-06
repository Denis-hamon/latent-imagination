"""Clean Tier emission (story 4.3): artifact `clean-tier` with the hardening
report INSIDE (criteria, reject rate, floor verdict + caveat) — AD-13 inputs
cite the hardening-policy and license-inventory hashes.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

import pyarrow.parquet as pq
from core_schema.errors import SchemaError
from store.emit import compute_store_version, write_artifact

from corpus.clean import CleanItem, FloorVerdict, clean_table

ARTIFACT_TYPE = "corpus-item-set"


def _git_head(root: Path) -> str:
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    head = r.stdout.strip()
    if r.returncode != 0 or len(head) != 40:
        raise SchemaError("LI-CORPUS-009", "cannot resolve code_commit", {"root": str(root)})
    return head


def emit_clean_tier(
    store_root: Path,
    kept: list[CleanItem],
    rejects: list[dict],
    by_reason: dict,
    verdict: FloorVerdict,
    *,
    artifact_version: str,
    hardening_policy_path: Path,
    license_inventory_path: Path,
    candidates_total: int,
    source_hashes: dict[str, str],
    known_hackable_used: bool,
    code_commit: str,
    corpus_version: str = "corpus-v0",
    repo_root: Path | None = None,
) -> dict:
    """Write <id>/<version>/{items.parquet, hardening-report.json} + manifest.

    Integrity (4.3 CR): reconciliation is enforced — kept+rejects must equal
    candidates_total and verdict.kept must equal the shipped count; the cited
    policy hash binds the values the build actually derived from it; the
    report names ONLY the rejectors that genuinely ran; code_commit is
    mandatory and caller-supplied (no silent dirty-tree HEAD reads)."""
    if not kept:
        raise SchemaError("LI-CORPUS-009", "refusing to emit an empty clean tier", {})
    if len(kept) + len(rejects) != candidates_total:
        raise SchemaError(
            "LI-CORPUS-009", "candidates_total does not reconcile with kept+rejected",
            {"kept": len(kept), "rejects": len(rejects), "candidates_total": candidates_total},
        )
    if verdict.kept != len(kept):
        raise SchemaError("LI-CORPUS-009", "floor verdict disagrees with the shipped set",
                          {"verdict_kept": verdict.kept, "kept": len(kept)})
    if not verdict.in_band and not verdict.caveat:
        raise SchemaError(
            "LI-CORPUS-009", "sub-floor build without the header caveat is refused", {"kept": verdict.kept}
        )
    reject_rate = len(rejects) / max(candidates_total, 1)
    ran = ["f2p-infra-config", "test-only-patch", "no-f2p-tests", "per-item license allowlist"]
    if known_hackable_used:
        ran.insert(2, "known-weak overlap")
    report = {
        "header_caveat": verdict.caveat or None,
        "criteria": "probe/hardening.py reject_reasons — ACTUALLY RUN: " + "; ".join(ran),
        "candidates": candidates_total,
        "kept": len(kept),
        "rejected": len(rejects),
        "reject_rate": round(reject_rate, 4),
        "by_reason": by_reason,
        "floor": verdict.model_dump(),
    }
    with tempfile.TemporaryDirectory() as tmp:
        parquet = Path(tmp) / "items.parquet"
        pq.write_table(clean_table(kept), parquet)
        report_path = Path(tmp) / "hardening-report.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        inputs = {
            "store_snapshot": compute_store_version(store_root),
            "ruleset_version": sha256(Path(hardening_policy_path).read_bytes()).hexdigest(),
            "code_commit": code_commit,
            "seeds": {},
            "license_inventory_hash": sha256(Path(license_inventory_path).read_bytes()).hexdigest(),
            "source_hashes": source_hashes,
            "corpus_version": corpus_version,
        }
        res = write_artifact(
            "corpus", ARTIFACT_TYPE, "clean-tier", artifact_version,
            [parquet, report_path], inputs, store_root,
        )
    return res.manifest
