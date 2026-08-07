"""Shared test fixture: a structurally-valid pinned snapshot (probe-predictor-v0).

Tests across gate/ranking/e2e build from HERE — one place to evolve the
artifact schema (the 3-copy drift the 8.2 CR caught)."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path


def make_pinned_snapshot(root: Path, *, corpus_version: str = "corpus-v0"):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    art = {
        "predictor_version": "probe-predictor-v0",
        "corpus_version": corpus_version,
        "measured": {"precision": 0.6271, "note": "Epic-3 matched-control; sub-bar by design (branch iii)"},
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "n_features": 2**12,
                       "alternate_sign": False, "norm": "l2", "lowercase": True,
                       "token_pattern": r"\b\w\w+\b"},
        "model": {"kind": "logreg-sigmoid", "intercept": 0.5, "coefficients": [0.0] * 2**12},
    }
    (root / "META.json").write_text(json.dumps(
        {"layout_version": "store-layout-v1", "store_version": "a" * 64}))
    blob = json.dumps(art, allow_nan=False)
    (root / "predictor.json").write_text(blob)
    return root, sha256(blob.encode()).hexdigest()
