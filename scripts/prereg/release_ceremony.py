"""Release ceremony — measurement-only publication package, end-to-end.

Assemble → chain → anchor → write to the (node-local) WORM bucket → ledger.

Run ON the node (it has MinIO + network). Read-only elsewhere.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from prereg.chain import assemble_chain

STAGE = "publication"


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def build_release_artifacts(workdir: Path, store_root: Path) -> dict:
    """Copy the published set into a release store + tarball it."""
    gov = workdir / "governance"
    pkg_dir = gov / "probe-design"
    release_id = "probe-measurement-2026-08-05"
    out_dir = store_root / "releases" / release_id / "v0"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Tarball of the governance packet (design + decisions + controls + runs)
    tarball = out_dir / f"{release_id}.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(pkg_dir, arcname="probe-design")

    # manifest of the object
    rel_manifest = {
        "artifact_id": release_id,
        "artifact_type": "release-manifest",
        "layout_version": "store-layout-v1",
        "artifact_class": "reproducible",
        "producer": STAGE,
        "inputs": {
            "store_snapshot": _sha(tarball),
            "ruleset_version": "rules-v1",
            "code_commit": _git_head(workdir),
            "seeds": {},
        },
        "files": [
            {
                "path": tarball.name,
                "sha256": _sha(tarball),
                "bytes": tarball.stat().st_size,
            }
        ],
    }
    manifest_dir = out_dir.parent / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    mpath = manifest_dir / f"{release_id}.v0.artifact.json"
    mpath.write_text(json.dumps(rel_manifest, indent=2, sort_keys=True) + "\n")

    return {
        "release_hash": _sha(tarball),
        "tarball": tarball,
        "manifest": rel_manifest,
        "manifest_path": mpath,
        "release_id": release_id,
    }


def _git_head(root: Path) -> str:
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or ("0" * 40)


def anchor_chain(workdir: Path, artifacts: dict, store_root: Path) -> dict:
    chain = assemble_chain(
        release_hash=artifacts["release_hash"],
        bundle_hash="0" * 64,  # no replay bundle for this publication; documented
        snapshot_hash=artifacts["release_hash"],  # the snapshot IS the release
        ruleset_hash=_sha(workdir / "packages/labeling/src/labeling/rules_v1.py"),
        code_commit=_git_head(workdir),
    )
    chain_path = store_root / "chains" / f"{chain.chain_hash[:16]}.json"
    chain_path.parent.mkdir(parents=True, exist_ok=True)
    chain_path.write_text(json.dumps(chain.to_dict(), indent=2, sort_keys=True) + "\n")

    # Anchor via the adapter (network happens ONLY here — edge hop)
    sys.path.insert(0, str(workdir / "packages/adapters/ots-anchor/src"))
    try:
        from ots_anchor.anchor import anchor

        proof_path = str(store_root / "proofs" / f"{chain.chain_hash[:16]}.ots")
        rec = anchor(chain.chain_hash, proof_path)
        mode = "ots-live"
    except Exception as e:
        from ots_anchor.anchor import anchor_offline_simulated

        proof_path = str(store_root / "proofs" / f"{chain.chain_hash[:16]}.sim.ots")
        rec = anchor_offline_simulated(chain.chain_hash, proof_path)
        mode = f"ots-simulated ({type(e).__name__})"
    return {"chain": chain.to_dict(), "record": rec.__dict__, "anchor_mode": mode}


def publish_to_worm_bucket(artifacts: dict, anchor_payload: dict) -> str:
    """Push the tarball into the node-local MinIO releases bucket (WORM)."""
    path = "/tmp/release-upload/"
    Path(path).mkdir(parents=True, exist_ok=True)
    local = Path(path) / artifacts["tarball"].name
    local.write_bytes(artifacts["tarball"].read_bytes())
    name = artifacts["tarball"].name
    proc = subprocess.run(
        [
            "docker", "cp", str(local), f"minio:/tmp/{name}",
        ],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"docker cp to minio failed: {proc.stderr}")
    up = subprocess.run(
        ["docker", "exec", "minio", "mc", "cp", f"/tmp/{name}", f"local/latent-imagination-releases/{name}"],
        capture_output=True, text=True, check=False,
    )
    if up.returncode != 0:
        raise RuntimeError(f"mc cp into releases bucket failed: {up.stderr}")
    return f"minio://latent-imagination-releases/{name}"


def main() -> int:
    workdir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    store_root = Path(sys.argv[2] if len(sys.argv) > 2 else workdir / "data" / "release-store")
    store_root.mkdir(parents=True, exist_ok=True)

    print("[1/4] build release artifacts…")
    arts = build_release_artifacts(workdir, store_root)
    print(f"    release_hash: {arts['release_hash'][:16]}…  tarball: {arts['tarball'].stat().st_size}B")

    print("[2/4] assemble + anchor the chain…")
    anchor_payload = anchor_chain(workdir, arts, store_root)
    print(f"    chain_hash: {anchor_payload['chain']['chain_hash'][:16]}…  mode: {anchor_payload['anchor_mode']}")

    print("[3/4] write to the WORM bucket (MinIO on this node)…")
    uri = publish_to_worm_bucket(arts, anchor_payload)
    print(f"    written: {uri}")

    print("[4/4] record into the ledger…")
    from prereg.ledger import anchor_entry, append_entry

    ledger = store_root / "prereg-ledger.jsonl"
    append_entry(
        ledger,
        anchor_entry(
            chain_hash=anchor_payload["chain"]["chain_hash"],
            ruleset_hash=anchor_payload["chain"]["ruleset"],
            anchored_at=anchor_payload["record"]["anchored_at"],
            proof_ref=anchor_payload["record"]["ots_proof_ref"],
        ),
    )
    print("    ledger row appended")

    print("CEREMONY COMPLETE")
    print(json.dumps(
        {
            "release_hash": arts["release_hash"],
            "chain_hash": anchor_payload["chain"]["chain_hash"],
            "anchor_mode": anchor_payload["anchor_mode"],
            "bucket_uri": uri,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
