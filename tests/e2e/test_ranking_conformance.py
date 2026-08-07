"""Story 8.1 CR: the ranking seam REALLY accepts the gate's pinned predictor —
not by signature coincidence, by construction test (imports both packages)."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from gate.ports import load_pinned_snapshot
from gate.predict import PinnedPredictor
from tools_ranking.core import rank_candidates, serialize_ordering


def test_pinned_predictor_satisfies_the_ranking_scorer_protocol(tmp_path):
    art = {
        "predictor_version": "probe-predictor-v0", "corpus_version": "corpus-v0",
        "measured": {"precision": 0.6271},
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "n_features": 2**12,
                       "alternate_sign": False, "norm": "l2", "lowercase": True,
                       "token_pattern": r"\b\w\w+\b"},
        "model": {"kind": "logreg-sigmoid", "intercept": 0.5, "coefficients": [0.0] * 2**12},
    }
    (tmp_path / "META.json").write_text(json.dumps(
        {"layout_version": "store-layout-v1", "store_version": "a" * 64}))
    blob = json.dumps(art, allow_nan=False)
    (tmp_path / "predictor.json").write_text(blob)
    snap = load_pinned_snapshot(tmp_path, expected_predictor_hash=sha256(blob.encode()).hexdigest())
    pred = PinnedPredictor.from_snapshot(snap)
    rows = rank_candidates(pred, [{"id": "a", "patch_diff": "diff --git a/x b/x\n+1\n"},
                                  {"id": "b", "patch_diff": "diff --git a/y b/y\n+2\n"}])
    assert len(rows) == 2
    assert serialize_ordering(rows)  # the real seam drives the tool
