"""Ranking deployment wiring (story 8.2, AD-1): pinned port, local log, no exec."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from tools_ranking.serve import RankingServer


def _server(tmp_path):
    art = {
        "predictor_version": "probe-predictor-v0", "corpus_version": "corpus-v0",
        "measured": {"precision": 0.6271},
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "n_features": 2**12,
                       "alternate_sign": False, "norm": "l2", "lowercase": True,
                       "token_pattern": r"\b\w\w+\b"},
        "model": {"kind": "logreg-sigmoid", "intercept": 0.5, "coefficients": [0.0] * 2**12},
    }
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "META.json").write_text(json.dumps({"layout_version": "store-layout-v1",
                                                "store_version": "a" * 64}))
    blob = json.dumps(art, allow_nan=False)
    (snap / "predictor.json").write_text(blob)
    return RankingServer.load(snap, expected_predictor_hash=sha256(blob.encode()).hexdigest(),
                              log_path=tmp_path / "dep" / "decisions.jsonl")


def test_rank_logs_candidates_ranked_event(tmp_path):
    server = _server(tmp_path)
    rows = server.rank([{"id": "a", "patch_diff": "diff --git a/x b/x\n+1\n"},
                        {"id": "b", "patch_diff": "diff --git a/y b/y\n+2\n"}])
    assert len(rows) == 2
    log = (tmp_path / "dep" / "decisions.jsonl").read_text()
    rec = json.loads(log)
    assert rec["kind"] == "candidates_ranked"
    assert rec["payload"]["predictor_hash"] == server.snapshot.predictor_hash
    assert rec["payload"]["n_candidates"] == 2


def test_no_execution_surface_exists_in_the_package():
    import re

    import tools_ranking.core as c
    import tools_ranking.serve as s

    calls = re.compile(r"\b(subprocess|os\.system|pty)\b|(?:exec|eval)\s*\(")
    for mod in (c, s):
        src = Path(mod.__file__).read_text()
        found = calls.search(src)
        assert not found, f"{mod.__name__} holds an execution surface: {found.group(0)}"


def test_snapshot_is_pinned_read_port(tmp_path):
    server = _server(tmp_path)
    assert server.snapshot.predictor_hash
    assert server.snapshot.corpus_version == "corpus-v0"
