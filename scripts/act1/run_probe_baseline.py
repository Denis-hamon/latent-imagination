"""Probe run — baseline arm on the REAL matrix (one command, fully recorded)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def run_baseline_probe(workdir: Path) -> dict:
    from sklearn.linear_model import LogisticRegression

    root = Path(workdir)
    matrix = json.loads((root / "governance/probe-design/probe-matrix.json").read_text())
    split = json.loads((root / "governance/probe-design/split-manifest.json").read_text())

    eval_ids = set(split["eval_instance_ids"])
    train_ids = set(split["train_instance_ids"])
    # The fused split was computed over namespaced matrix ids ("verified::…",
    # "smith::…::model") — match on those, NOT bare instance ids.

    train_rows = [r for r in matrix if r["instance_id"] in train_ids]
    eval_rows = [r for r in matrix if r["instance_id"] in eval_ids]

    from probe.embeddings import embed_documents
    from probe.features import render_document

    Xtr = embed_documents([render_document(r) for r in train_rows])
    Xev = embed_documents([render_document(r) for r in eval_rows])
    ytr = [r["label"] for r in train_rows]
    yev = [r["label"] for r in eval_rows]

    model = LogisticRegression(C=1.0, max_iter=2000, random_state=20260805, class_weight="balanced")
    model.fit(Xtr, ytr)
    pred = model.predict(Xev)
    tp = int(((pred == 1) & (np.array(yev) == 1)).sum())
    fp = int(((pred == 1) & (np.array(yev) == 0)).sum())
    fn = int(((pred == 0) & (np.array(yev) == 1)).sum())
    n_pos_pred = tp + fp
    precision = tp / n_pos_pred if n_pos_pred else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    # Wilson 95% CI for precision
    from scipy.stats import norm

    z = norm.ppf(0.975)
    if n_pos_pred:
        p = precision
        den = 1 + z**2 / n_pos_pred
        center = (p + z**2 / (2 * n_pos_pred)) / den
        half = (z * ((p * (1 - p) / n_pos_pred + z**2 / (4 * n_pos_pred**2)) ** 0.5)) / den
        ci = (max(0.0, center - half), min(1.0, center + half))
    else:
        ci = (0.0, 1.0)

    report = {
        "arm": "baseline",
        "n_train": len(train_rows),
        "n_eval": len(eval_rows),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "precision_wilson95": [round(x, 4) for x in ci],
        "recall": round(recall, 4),
        "registered_bar": 0.8889,
        "verdict_rule": "precision >= registered_bar (inclusive) AND margin vs arms",
    }

    # FR-14: stylistic controls, computed alongside the headline
    from probe.controls import stratified_precision

    controls = stratified_precision(
        [(r["label"], int(p), r["patch"], r["source"]) for r, p in zip(eval_rows, pred)]
    )
    report["controls"] = controls
    return report


if __name__ == "__main__":
    rep = run_baseline_probe(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    print(json.dumps(rep, indent=2))
