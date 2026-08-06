"""Corpus release assembly (story 4.4, FR-17) — a manifest OF manifests.

`corpus-publish` cites every constituent by content hash and RECOMPUTES NOTHING:
tier artifacts are read from the store's own manifests, governance docs are
hashed as committed, and the distribution block says exactly where the release
stands (WORM ceremony = node window; Zenodo/HF = adapters still pending — the
manifest says so, no theater).

The artifact is reproducible-class (content-only, AD-7).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError
from store.emit import write_artifact

ARTIFACT_TYPE = "corpus-release"
SCHEMA_VERSION = "corpus-release-v1"


def _sha(p: Path) -> str:
    try:
        return sha256(Path(p).read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise SchemaError("LI-CORPUS-012", "release constituent missing", {"path": str(p)}) from exc


def _git_head(root: Path) -> str:
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                       capture_output=True, text=True, check=False)
    head = r.stdout.strip()
    if r.returncode != 0 or len(head) != 40:
        raise SchemaError("LI-CORPUS-012", "cannot resolve code_commit", {"root": str(root)})
    return head


def validate_manifest_citations(manifest: dict) -> None:
    """AD-13/FR-17 teeth: any manifest whose inputs touch the corpus MUST cite
    `corpus_version`, non-empty and parseable (corpus-v<N>)."""
    inputs = manifest.get("inputs") or {}
    touches = any("corpus" in str(k).lower() for k in inputs) or (
        manifest.get("artifact_type", "").startswith("corpus")
    )
    if not touches:
        return
    version = inputs.get("corpus_version") or manifest.get("corpus_version")
    if not isinstance(version, str) or not version.startswith("corpus-v") or not version[8:].isdigit():
        raise SchemaError(
            "LI-CORPUS-012",
            "corpus-touching manifest without a parseable corpus_version citation",
            {"artifact_id": manifest.get("artifact_id"), "got": version},
        )


def assemble_corpus_release(
    store_root: Path,
    governance_root: Path,
    *,
    major: int = 0,
    code_commit: str,
    repo_root: Path | None = None,
) -> dict:
    store_root = Path(store_root)
    governance_root = Path(governance_root)
    corpus_version = f"corpus-v{major}"

    tiers = []
    manifests_dir = store_root / "canonical" / "manifests"
    if manifests_dir.is_dir():
        for m in sorted(manifests_dir.glob("*.artifact.json")):
            man = json.loads(m.read_text())
            if man.get("artifact_type") != "corpus-item-set":
                continue
            tier = {
                "artifact_id": man["artifact_id"],
                "artifact_version": man["artifact_version"],
                "files": man["files"],
                "inputs_hashes": {k: v for k, v in (man.get("inputs") or {}).items()
                                  if k in ("ruleset_version", "license_inventory_hash",
                                           "exclusion_rule_hash", "source_hashes")},
            }
            for f in man["files"]:
                p = store_root / f["path"]
                if p.is_file() and sha256(p.read_bytes()).hexdigest() != f["sha256"]:
                    raise SchemaError(
                        "LI-CORPUS-012", "tier artifact content drifted from its manifest",
                        {"path": str(p)},
                    )
            tiers.append(tier)
    if not tiers:
        raise SchemaError("LI-CORPUS-012", "no corpus tiers in the store — nothing to publish", {})

    payload = {
        "schema_version": SCHEMA_VERSION,
        "corpus_version": corpus_version,
        "tiers": tiers,
        "license_inventory_hash": _sha(governance_root / "corpus" / "license-inventory-v1.json"),
        "exclusion_rule_hash": _sha(governance_root / "corpus" / "exclusion-rule-v1.toml"),
        "hardening_policy_hash": _sha(governance_root / "corpus" / "hardening-policy-v1.toml"),
        "policy_hash": _sha(governance_root / "corpus" / "harvest-policy-v1.toml"),
        "distribution": {
            "worm_bucket": "node MinIO — ceremony window (owner-run)",
            "zenodo": "ADAPTER PENDING (story 2.6 task 4) — not yet pushed",
            "hf_hub": "ADAPTER PENDING (story 2.6 task 4) — not yet pushed",
            "github": "releases on Denis-hamon/latent-imagination",
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "corpus-release.json"
        f.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        inputs = {
            "store_snapshot": None,
            "ruleset_version": payload["policy_hash"],
            "code_commit": code_commit or _git_head(repo_root or Path.cwd()),
            "seeds": {},
            "corpus_version": corpus_version,
            "tiers_cited": [f"{t['artifact_id']}/{t['artifact_version']}" for t in tiers],
        }
        from store.emit import compute_store_version

        inputs["store_snapshot"] = compute_store_version(store_root)
        manifest_dict = {"artifact_type": ARTIFACT_TYPE, "artifact_id": f"corpus-release-v{major}",
                         "inputs": inputs}
        validate_manifest_citations(manifest_dict)
        res = write_artifact(
            "corpus", ARTIFACT_TYPE, f"corpus-release-v{major}", "v0",
            [f], inputs, store_root,
        )
    return res.manifest
