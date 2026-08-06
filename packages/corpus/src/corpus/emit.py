"""Corpus store emission (AD-4: corpus owns corpus artifacts; AD-13: the inputs
block cites the landing manifests + the harvest-policy hash + code commit).

Item-sets are reproducible-class artifacts living in the canonical zone, so the
content-addressed store_version covers them (store-layout-v1/contract).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from core_schema.errors import SchemaError
from store.emit import compute_store_version, write_artifact

from corpus.exclusion import apply_exclusion, assert_no_overlap_cited, load_rule
from corpus.noisy import NoisyItem

ARTIFACT_TYPE = "corpus-item-set"


def _git_head(root: Path) -> str:
    """The producing code's commit — fail loud, never fabricate (P17)."""
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    head = r.stdout.strip()
    if r.returncode != 0 or len(head) != 40:
        raise SchemaError(
            "LI-CORPUS-005",
            "cannot resolve code_commit (pass code_commit= explicitly or run in a git work tree)",
            {"root": str(root), "rc": r.returncode},
        )
    return head


def policy_sha256(policy_path: Path) -> str:
    try:
        return sha256(Path(policy_path).read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise SchemaError("LI-CORPUS-001", "harvest policy not found", {"path": str(policy_path)}) from exc


def items_table(items: list[NoisyItem]) -> pa.Table:
    rows = [i.model_dump(mode="json") for i in items]
    schema = pa.schema(
        [
            ("item_id", pa.string()),
            ("task_id", pa.string()),
            ("repo", pa.string()),
            ("head_sha", pa.string()),
            ("workflow_run_id", pa.int64()),
            ("pr_number", pa.int64()),
            ("conclusion", pa.string()),
            ("license", pa.string()),
            ("attempt_start_utc", pa.string()),
            ("patch_sha256", pa.string()),
            ("sanitize_counts", pa.string()),  # canonical JSON (counts are small)
            ("provenance_path", pa.string()),
        ]
    )
    cols = {f: [r[f] if not isinstance(r[f], dict) else json.dumps(r[f], sort_keys=True) for r in rows] for f in schema.names}
    return pa.table(cols, schema=schema)


def emit_noisy_item_set(
    store_root: Path,
    items: list[NoisyItem],
    *,
    artifact_id: str,
    artifact_version: str,
    policy_path: Path,
    landing_root: Path,
    exclusion_rule_path: Path,
    code_commit: str | None = None,
    repo_root: Path | None = None,
) -> dict:
    """Write <id>/<version>/{items.parquet, leakage-audit.json} + manifest.

    The exclusion rule (story 4.2) is MANDATORY and SINGULAR: `load_rule`
    verifies the cited constituents' hash and returns THE bound set — there is
    no second, uncited file (CR 4.2). Items are filtered, the audit ships
    inside the artifact, and the kept set is re-checked against a FRESH read
    of the cited file (LI-CORPUS-006) — defense in depth, non-tautological AC2.
    Idempotent by store rules.
    """
    if not items:
        raise SchemaError("LI-CORPUS-004", "refusing to emit an empty item-set", {})
    _rule, constituents, constituents_path = load_rule(exclusion_rule_path)
    kept, excluded, audit = apply_exclusion(items, constituents)
    audit.update(assert_no_overlap_cited(kept, constituents_path))  # fresh-read check, AC2
    if not kept:
        raise SchemaError(
            "LI-CORPUS-008", "exclusion consumed the ENTIRE set — nothing to emit",
            {"excluded": len(excluded)},
        )

    with tempfile.TemporaryDirectory() as tmp:
        parquet = Path(tmp) / "items.parquet"
        pq.write_table(items_table(kept), parquet)
        audit_path = Path(tmp) / "leakage-audit.json"
        audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
        landing_manifests = sorted(
            sha256(p.read_bytes()).hexdigest()
            for p in Path(landing_root).glob("ci-logs/*/.harvest-manifest.json")
        )
        inputs = {
            "store_snapshot": compute_store_version(store_root),
            "ruleset_version": policy_sha256(policy_path),
            "code_commit": code_commit or _git_head(repo_root or Path.cwd()),
            "seeds": {},
            "landing_manifests": landing_manifests,
            "exclusion_rule_hash": sha256(Path(exclusion_rule_path).read_bytes()).hexdigest(),
            "leakage_audit": {"kept": audit["kept"], "excluded": audit["excluded"],
                               "zero_overlap": audit["zero_overlap"]},
        }
        res = write_artifact(
            "corpus",
            ARTIFACT_TYPE,
            artifact_id,
            artifact_version,
            [parquet, audit_path],
            inputs,
            store_root,
        )
    return res.manifest
