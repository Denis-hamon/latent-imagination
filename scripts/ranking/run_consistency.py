"""Run the ordering-consistency evaluation (story 8.3): the re-runnable path.

Reads a records file ({task_id, predicted, realized}) — real records are
produced by the evaluation window pairing gate scores with realized F2P
outcomes; a small committed fixture ships so ANY fresh clone can execute the
machinery end-to-end (see tests/e2e + governance/ranking/).

Usage: uv run python scripts/ranking/run_consistency.py --records <json> --store <dir>
"""

from __future__ import annotations

import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path

from core_schema.errors import SchemaError
from tools_ranking.consistency import evaluate_split, publish_consistency_report

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--store", default=str(REPO / "data" / "store"))
    ap.add_argument("--split-manifest", default=str(REPO / "governance" / "ranking" / "split-2026-08-06.json"))
    args = ap.parse_args()

    records = json.loads(Path(args.records).read_text())
    report = evaluate_split(records)
    protocol = REPO / "governance" / "ranking" / "consistency-protocol-v1.toml"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                          text=True, check=False).stdout.strip()
    try:
        man = publish_consistency_report(
            report, Path(args.store), report_version="v0",
            dataset_versions={"clean-tier": "clean-tier/v0",
                              "probe-split/calibration": "governance/probe-design/split-manifest.json"},
            protocol_sha256=sha256(protocol.read_bytes()).hexdigest(),
            corpus_version="corpus-v0", code_commit=head or "0" * 40,
            split_manifest_path=Path(args.split_manifest),
        )
        print(json.dumps({"published": man["artifact_id"], "macro_tau": report["macro_tau"],
                          "n_degenerate": report["n_degenerate"]}, indent=2))
    except SchemaError as e:
        # all-degenerate or un-citable split → publish-with-caveat posture (never silent)
        print(json.dumps({"not_published": f"{e.code}: {e.message}", "report": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
