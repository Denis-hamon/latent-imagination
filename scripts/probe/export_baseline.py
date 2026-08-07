"""Export the advisory baseline into a pinned arm-artifact (Act II window).

Trains per the EPIC-3 sealed config (ArmConfig defaults), measures the SAME
eval slice, writes the store artifact via write_artifact("probe", "arm-artifact")
(+ a gate-handoff snapshot at data/act2-arm0/) and prints the artifact hash.

HONESTY: the recorded precision is the W measured head (0.6271 at 5 digits —
matches the sealed headline); the artifact says sub-bar. Run on the node:
  uv run python scripts/probe/export_baseline.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from probe.arms.baseline import ArmConfig, train_and_evaluate
from probe.arms.baseline_export import export_baseline
from probe.embeddings import embed_documents
from probe.features import render_document
from store.emit import write_artifact

ROOT = Path(__file__).resolve().parents[2]


def _prep():
    m = json.loads((ROOT / "governance/probe-design/matched-matrix.json").read_text())
    s = json.loads((ROOT / "governance/probe-design/matched-split-manifest.json").read_text())
    by_id = {}
    for row in m:
        by_id.setdefault(row["instance_id"], row)
    tr = [by_id[i] for i in s["train_instance_ids"] if i in by_id]
    ev = [by_id[i] for i in s["eval_instance_ids"] if i in by_id]
    return tr, ev


def main() -> int:
    tr, ev = _prep()
    Xtr = embed_documents([render_document(r) for r in tr])
    Xev = embed_documents([render_document(r) for r in ev])
    ytr = [r["label"] for r in tr]
    yev = [r["label"] for r in ev]
    res = train_and_evaluate(Xtr, ytr, Xev, yev, config=ArmConfig())
    print({"precision": round(res.precision, 4), "recall": round(res.recall, 4),
           "n_train": len(tr), "n_eval": len(ev), "artifact_hash": res.artifact_hash[:12]})

    # refit with the sealed config to have the fitted model in hand
    from sklearn.linear_model import LogisticRegression

    fitted = LogisticRegression(
        C=ArmConfig().c_value, max_iter=ArmConfig().max_iter,
        random_state=ArmConfig().seed, class_weight="balanced",
    )
    fitted.fit(Xtr, ytr)

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True, check=False).stdout.strip()

    # integrity first: Wilson CI from the published Epic-3 reference run
    ref = json.loads((ROOT / "governance/probe-design/runs/baseline-matched-control-2026-08-05.json").read_text())
    _art = export_baseline(
        fitted, n_features=4096,
        measured={
            "precision": res.precision, "precision_wilson95": ref["precision_wilson95"],
            "recall": res.recall, "f1": res.f1, "n_train": len(tr), "n_eval": len(ev),
            "posture": "SUB-BAR (verdict 2026-08-05 branch iii) — advisory-scaffold, not certified",
            "sealed_headline_2026_08_05": 0.6271,
            "reference_run": "governance/probe-design/runs/baseline-matched-control-2026-08-05.json",
        },
        corpus_version="corpus-v0",
        out_path=ROOT / "governance" / "act2" / "arm-artifacts" / "predictor-v0" / "predictor.json",
        code_commit=head,
    )
    # The store artifact wraps the exported predictor JSON — AD-13 inputs block,
    # all hashes real (the 4.3 CR lesson: no nulls on the AD-13 surface).
    from hashlib import sha256 as _sha

    from store.emit import compute_store_version

    pred_json = ROOT / "governance" / "act2" / "arm-artifacts" / "predictor-v0" / "predictor.json"
    store_root = ROOT / "data" / "release-store"
    inputs = {
        "store_snapshot": compute_store_version(store_root),
        "ruleset_version": _sha((ROOT / "governance/probe-design/decision.toml").read_bytes()).hexdigest(),
        "code_commit": head,
        "seeds": {"model": ArmConfig().seed},
        "matrix": "governance/probe-design/matched-matrix.json",
        "split": "governance/probe-design/matched-split-manifest.json",
    }
    rec = write_artifact(
        "probe", "arm-artifact", "probe-predictor-v0", "v0",
        [pred_json],
        inputs,
        store_root,
    )
    assert rec.manifest["inputs"] == inputs  # written == computed (no silent store-side edit)
    print("artifact manifest written:", rec.manifest_path)
    print("predictor sha256:", _sha(pred_json.read_bytes()).hexdigest()[:16])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
