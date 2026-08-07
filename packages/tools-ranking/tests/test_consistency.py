"""Ordering-consistency evaluation (story 8.3, FR-24): tau-b hand-verified,
degenerate rule enforced, split machinery deterministic and disjoint."""

from __future__ import annotations

import json
from hashlib import sha256

import pytest
from core_schema.errors import SchemaError
from tools_ranking.consistency import (
    evaluate_split,
    heldout_split,
    kendall_tau_b,
    publish_consistency_report,
)


class TestTauB:
    def test_perfect_concordance(self):
        # predicted lower = better; realized True = better; same ordering → +1
        assert kendall_tau_b({"a": 0.1, "b": 0.9}, {"a": True, "b": False}) == pytest.approx(1.0)

    def test_full_inversion(self):
        assert kendall_tau_b({"a": 0.1, "b": 0.9}, {"a": False, "b": True}) == pytest.approx(-1.0)

    def test_hand_computed_tie_case(self):
        # pairs: (a,b) tied BOTH sides; (a,c),(b,c) concordant.
        # n0=3, ties_pred=1, ties_real=1 → tau = 2/sqrt((3-1)*(3-1)) = 1.0.
        tau = kendall_tau_b({"a": 0.5, "b": 0.5, "c": 0.9}, {"a": True, "b": True, "c": False})
        assert tau == pytest.approx(1.0)

    def test_balanced_discordance_is_exactly_zero(self):
        # (a,b) concordant; (a,c) realized-tie; (b,c) discordant → concordant sum 0
        tau = kendall_tau_b({"a": 0.1, "b": 0.2, "c": 0.3},
                            {"a": True, "b": False, "c": True})
        assert tau == pytest.approx(0.0)

    def test_degenerate_all_tied_pred_returns_none(self):
        assert kendall_tau_b({"a": 0.5, "b": 0.5}, {"a": True, "b": False}) is None

    def test_degenerate_realized_all_valid(self):
        assert kendall_tau_b({"a": 0.1, "b": 0.9}, {"a": True, "b": True}) is None

    def test_mismatched_candidate_sets_refused(self):
        with pytest.raises(SchemaError):
            kendall_tau_b({"a": 0.1, "b": 0.2}, {"a": True, "c": False})


def test_evaluate_split_aggregates_and_counts():
    recs = [
        {"task_id": "t1", "predicted": {"a": 0.1, "b": 0.9}, "realized": {"a": True, "b": False}},
        {"task_id": "t2", "predicted": {"a": 0.5, "b": 0.5}, "realized": {"a": True, "b": False}},
        {"task_id": "t3", "predicted": {"a": 0.2, "b": 0.1}, "realized": {"a": True, "b": False}},
    ]
    out = evaluate_split(recs)
    assert out["statistic"] == "kendall-tau-b"
    assert out["n_degenerate"] == 1
    assert out["macro_tau"] == pytest.approx((1.0 + (-1.0)) / 2)
    assert out["per_task"]["t2"] is None


def test_all_degenerate_split_records_none_means_publish_with_caveat():
    recs = [{"task_id": "t", "predicted": {"a": 0.5, "b": 0.5}, "realized": {"a": True, "b": False}}]
    out = evaluate_split(recs)
    assert out["macro_tau"] is None  # publication carries the caveat, never a coerced number


def test_heldout_split_deterministic_and_disjoint():
    ids = [f"t{i}" for i in range(300)]
    a = heldout_split(ids, seed=20260806, exclude=frozenset({"t1", "t2"}))
    assert a == heldout_split(ids, seed=20260806, exclude=frozenset({"t1", "t2"}))
    assert "t1" not in a and "t2" not in a
    assert a != heldout_split(ids, seed=1)
    assert len(a) == max(1, round(298 * 0.2))  # registered small-pool rule


def test_publish_report_writes_store_artifact(tmp_path):
    rep = evaluate_split([{"task_id": "t1", "predicted": {"a": 0.1, "b": 0.9},
                           "realized": {"a": True, "b": False}}])
    proto = (tmp_path / "proto.toml")
    proto.write_text("[p]\nx = 1\n")
    sm = tmp_path / "split.json"
    sm.write_text(json.dumps({"split_id": "test"}))
    m = publish_consistency_report(rep, tmp_path / "store", report_version="v0",
                                   dataset_versions={"clean-tier": "clean-tier/v0"},
                                   protocol_sha256=sha256(proto.read_bytes()).hexdigest(),
                                   corpus_version="corpus-v0", code_commit="c" * 40,
                                   split_manifest_path=sm)
    assert m["artifact_type"] == "ranking-report"
    assert m["producer"] == "tools-ranking"
    assert m["inputs"]["dataset_versions"]["clean-tier"] == "clean-tier/v0"
    assert (tmp_path / "store" / "canonical" / "ordering-consistency" / "v0" / "consistency-report.json").is_file()
