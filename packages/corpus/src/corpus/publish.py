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
import re
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


VERSION_RE = re.compile(r"corpus-v(0|[1-9][0-9]*)")  # ASCII, no leading zeros


def validate_manifest_citations(manifest: dict) -> None:
    """AD-13/FR-17 teeth: any manifest whose inputs touch the corpus MUST cite
    `corpus_version`, parseable. The STRUCTURAL copy of this rule lives in
    `store.validate` (no circular import) — keep both predicates in lockstep."""
    inputs = manifest.get("inputs") or {}
    touches = {"corpus_version", "corpus_tier", "tiers_cited"} & set(inputs) or (
        str(manifest.get("artifact_type", "")).startswith("corpus")
    )
    if not touches:
        return
    version = inputs.get("corpus_version")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
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
    release_revision: str = "v0",
    repo_root: Path | None = None,
) -> dict:
    store_root = Path(store_root)
    governance_root = Path(governance_root)
    if not isinstance(code_commit, str) or len(code_commit) != 40:
        raise SchemaError("LI-CORPUS-012", "code_commit is mandatory (caller-checked HEAD)",
                          {"got": code_commit})
    if not isinstance(major, int) or major < 0:
        raise SchemaError("LI-CORPUS-012", "major must be a non-negative int", {"got": major})
    corpus_version = f"corpus-v{major}"

    # latest version per tier id ONLY — a remediated release must cite the
    # corrected version, never the disavowed one (CR 4.4 high).
    manifests_dir = store_root / "canonical" / "manifests"
    by_id: dict[str, dict] = {}
    if manifests_dir.is_dir():
        for m in sorted(manifests_dir.glob("*.artifact.json")):
            try:
                man = json.loads(m.read_text())
            except ValueError as exc:
                raise SchemaError("LI-CORPUS-012", "tier manifest unreadable", {"path": str(m)}) from exc
            if man.get("artifact_type") != "corpus-item-set":
                continue
            vkey = man.get("artifact_version", "")
            n = int(vkey[1:]) if vkey.startswith("v") and vkey[1:].isdigit() else -1
            if n < 0:
                raise SchemaError("LI-CORPUS-012", "tier version unparseable", {"version": vkey})
            prev = by_id.get(man["artifact_id"])
            if prev is None or n > prev[0]:
                by_id[man["artifact_id"]] = (n, man)
    tiers = []
    for _aid, (_n, man) in sorted(by_id.items()):
        if not man.get("files"):
            raise SchemaError("LI-CORPUS-012", "tier manifest carries no files", {"artifact": _aid})
        for f in man["files"]:
            p = (store_root / f["path"]).resolve()
            try:
                p.relative_to(store_root.resolve())
            except ValueError as exc:
                raise SchemaError("LI-CORPUS-012", "tier file path escapes the store",
                                  {"path": f["path"]}) from exc
            if not p.is_file():
                raise SchemaError("LI-CORPUS-012", "tier file MISSING — drift by deletion",
                                  {"path": str(p)})
            if sha256(p.read_bytes()).hexdigest() != f["sha256"]:
                raise SchemaError("LI-CORPUS-012", "tier artifact content drifted from its manifest",
                                  {"path": str(p)})
        tiers.append({
            "artifact_id": man["artifact_id"],
            "artifact_version": man["artifact_version"],
            "files": man["files"],
            "inputs": man.get("inputs") or {},  # full citation — no key allowlist to rot
        })
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
            "code_commit": code_commit,
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
            "corpus", ARTIFACT_TYPE, f"corpus-release-v{major}", release_revision,
            [f], inputs, store_root,
        )
    return res.manifest
