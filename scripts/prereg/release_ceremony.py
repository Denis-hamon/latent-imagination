"""Release ceremony — measurement-only publication package, end-to-end.

Assemble → chain → anchor → write to the (node-local) WORM bucket → ledger.

Run ON the node (it has MinIO + network). Read-only elsewhere.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tarfile
from hashlib import sha256
from pathlib import Path

from prereg.chain import assemble_chain

STAGE = "publication"


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def build_release_artifacts(
    workdir: Path,
    store_root: Path,
    *,
    packet: Path | None = None,
    release_id: str = "probe-measurement-2026-08-05",
) -> dict:
    """Copy the published packet into a release store + tarball it.

    `packet` defaults to the probe packet (governance/probe-design) — the probe
    call-shape is unchanged; the corpus release passes its own packet dir (4.4).
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", release_id):
        raise SystemExit(f"invalid --release-id {release_id!r} (slug policy)")
    pkg_dir = (Path(packet).resolve() if packet else (workdir / "governance" / "probe-design").resolve())
    if not pkg_dir.is_dir() or not pkg_dir.name:
        raise SystemExit(f"--packet must be an existing directory with a name, got {packet!r}")
    out_dir = store_root / "releases" / release_id / "v0"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Tarball of the packet (arcname = the packet's real name, not a hardcode)
    tarball = out_dir / f"{release_id}.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(pkg_dir, arcname=pkg_dir.name)

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
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
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
    except Exception as e:  # noqa: BLE001 — degrade-with-disclosure is the design: ANY live-anchor
        # failure falls back to a simulated anchor, and the mode lands on the ledger + ceremony output.
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
    import argparse

    ap = argparse.ArgumentParser(description="Release ceremony (signed chain + WORM write)")
    ap.add_argument("workdir", nargs="?", default=".")
    ap.add_argument("store_root", nargs="?", default=None)
    ap.add_argument("--packet", default=None,
                    help="packet dir to ship (default: <workdir>/governance/probe-design)")
    ap.add_argument("--release-id", default="probe-measurement-2026-08-05")
    args = ap.parse_args()

    workdir = Path(args.workdir)
    store_root = Path(args.store_root) if args.store_root else workdir / "data" / "release-store"
    store_root.mkdir(parents=True, exist_ok=True)

    print("[1/4] build release artifacts…")
    arts = build_release_artifacts(
        workdir, store_root,
        packet=Path(args.packet) if args.packet else None,
        release_id=args.release_id,
    )
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
