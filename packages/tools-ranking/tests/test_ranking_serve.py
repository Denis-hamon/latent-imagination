"""Ranking deployment wiring (story 8.2 + CR): pinned port, OQ-10 implemented,
replayable log payload, early validation, package-wide exec-surface scan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from gate.testing import make_pinned_snapshot
from tools_ranking.serve import RankingServer

CANDS = [{"id": "a", "patch_diff": "diff --git a/x b/x\n+1\n"},
         {"id": "b", "patch_diff": "diff --git a/y b/y\n+2\n"}]


def _server(tmp_path, **kw):
    root, phash = make_pinned_snapshot(tmp_path / "snap")
    return RankingServer.load(root, expected_predictor_hash=phash,
                              log_path=tmp_path / "dep" / "decisions.jsonl", **kw)


class TestOQ10:
    def test_no_tier_means_abstain_and_log(self, tmp_path):
        server = _server(tmp_path)
        with pytest.raises(SchemaError) as ei:
            server.rank(CANDS, prediction_target_tier=None)
        assert ei.value.code == "LI-RANK-002"
        rec = json.loads((tmp_path / "dep" / "decisions.jsonl").read_text().strip())
        assert rec["kind"] == "prediction_refused"
        assert rec["payload"]["surface"] == "ranking"

    def test_designated_tier_ranks_and_logs_replayable_payload(self, tmp_path):
        server = _server(tmp_path)
        rows = server.rank(CANDS, prediction_target_tier="user_designated")
        rec = json.loads((tmp_path / "dep" / "decisions.jsonl").read_text().strip())
        assert rec["kind"] == "candidates_ranked"
        assert rec["payload"]["interface_version"] == "gate-iface-v1"
        for rr, row in zip(rec["payload"]["ranking"], rows, strict=True):
            assert rr["candidate_id"] == row.candidate_id
            assert abs(rr["score"] - row.score) < 1e-9
            assert rr["patch_sha256"] == row.patch_sha256
        assert "latency_s" in rec["payload"]
        assert rec["payload"]["predictor_disclosure"]["precision"] == 0.6271


class TestEarlyValidation:
    def test_bad_log_path_fails_at_load_not_mid_loop(self, tmp_path):
        root, phash = make_pinned_snapshot(tmp_path / "snap")
        with pytest.raises(SchemaError):
            RankingServer.load(root, expected_predictor_hash=phash, log_path=tmp_path / "x.log")
        store = tmp_path / "st"
        (store / "canonical").mkdir(parents=True)
        (store / "META.json").write_text('{}')
        with pytest.raises(SchemaError):
            RankingServer.load(root, expected_predictor_hash=phash,
                               log_path=store / "decisions.jsonl")


def test_no_execution_surface_in_ANY_package_module():
    """Construction proof scans every .py of the package — not two named files."""
    import re

    import tools_ranking

    ban = re.compile(r"\b(subprocess|os\.system)\b|(?:exec|eval)\s*\(|__import__\s*\(|getattr\(__builtins__")
    for f in Path(tools_ranking.__file__).parent.rglob("*.py"):
        hit = ban.search(f.read_text())
        assert not hit, f"{f.name}: execution surface ({hit.group(0)})"
