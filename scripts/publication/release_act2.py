"""Act II release driver: packet → SAME ceremony as Act I (story 6.4).

Assemble the packet (publication.act2), then run it through the standard
ceremony functions (scripts/prereg/release_ceremony.py): tarball, AD-5 chain
(never reimplemented), OTS anchor (fallback disclosed), WORM write at the node.

Usage (node window): uv run python scripts/publication/release_act2.py \
    --delta path/delta.json --rerun path/rerun-report.json --pins path/campaign-pins.json \
    --act1-hash <64hex>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delta", required=True)
    ap.add_argument("--rerun", required=True)
    ap.add_argument("--pins", required=True)
    ap.add_argument("--act1-hash", required=True)
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--release-id", default="act2-intervention-YYYY-MM-DD",
                    help="override the placeholder before the real run")
    args = ap.parse_args()
    root = Path(args.workdir).resolve()
    sys.path.insert(0, str(root / "scripts" / "prereg"))

    import subprocess
    import tempfile

    from publication.act2 import assemble_act2_release
    from release_ceremony import anchor_chain, build_release_artifacts

    with tempfile.TemporaryDirectory() as td:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                              capture_output=True, text=True, check=False).stdout.strip()
        packet = assemble_act2_release(
            Path(td) / "act2-packet",
            delta_json=Path(args.delta), rerun_report_json=Path(args.rerun),
            templates_dir=root / "governance" / "act2" / "verdict-templates",
            campaign_pins_json=Path(args.pins),
            act1_release_hash=args.act1_hash, code_commit=head,
        )
        print("packet assembled;", packet["preprint_branch"]["verdict"],
              "| sm3:", packet["sm3"]["outcome"])
        if args.release_id.endswith("YYYY-MM-DD"):
            raise SystemExit("override --release-id with the real date before the window run")
        store = root / "data" / "release-store"
        arts = build_release_artifacts(root, store, packet=Path(td) / "act2-packet",
                                       release_id=args.release_id)
        payload = anchor_chain(root, arts, store)
        print("chain:", payload["chain"]["chain_hash"][:16], "| anchor:", payload["anchor_mode"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
