"""Baseline predictor export (story 5.2, training side): the sklearn model
becomes ONE pinned, porta ble artifact — `predictor.json`, stdlib-scorable
(AD-11: the gate never installs sklearn).

probe-predictor-v0 format:
{predictor_version, corpus_version, created_by, measured, vectorizer, model}.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core_schema.errors import SchemaError

PREDICTOR_VERSION = "probe-predictor-v0"


def export_baseline(
    model: Any,
    *,
    n_features: int,
    measured: dict,
    corpus_version: str,
    out_path: Path,
    code_commit: str,
) -> dict:
    """Serialize a fitted sklearn LogisticRegression into the pinned artifact."""
    coef = getattr(model, "coef_", None)
    intercept = getattr(model, "intercept_", None)
    if coef is None or intercept is None:
        raise SchemaError("LI-PROBE-002", "model not fitted (coef_/intercept_ missing)", {})
    if getattr(coef, "shape", None) is None or len(coef.shape) != 2 or coef.shape[0] != 1:
        raise SchemaError("LI-PROBE-002",
                          "binary logistic only — multiclass would silently export class 0", {})
    w = [float(c) for c in coef[0]]
    if len(w) != n_features:
        raise SchemaError("LI-PROBE-002", "coef width ≠ n_features", {"w": len(w)})
    artifact = {
        "predictor_version": PREDICTOR_VERSION,
        "corpus_version": corpus_version,
        "created_by": {"stage": "probe.baseline", "code_commit": code_commit},
        "measured": measured,
        "vectorizer": {
            "kind": "sklearn.HashingVectorizer",
            "n_features": n_features,
            "alternate_sign": False,
            "norm": "l2",
            "lowercase": True,
            "token_pattern": r"\b\w\w+\b",
        },
        "model": {"kind": "logreg-sigmoid", "intercept": float(intercept[0]), "coefficients": w},
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.replace(out_path)
    return artifact
