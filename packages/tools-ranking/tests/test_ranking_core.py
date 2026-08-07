"""Ranking core (story 8.1, FR-23): order, explicit ties, byte determinism."""

from __future__ import annotations

import random

import pytest
from core_schema.errors import SchemaError
from tools_ranking.core import rank_candidates, serialize_ordering


class _ConstScorer:  # deterministic stand-in
    def __init__(self, table):
        self.table = table

    def score(self, document: str) -> float:
        return self.table[document]


CANDS = [
    {"id": "b", "patch_diff": "diff-b"},
    {"id": "a", "patch_diff": "diff-a"},
    {"id": "c", "patch_diff": "diff-c"},
]
SCORES = {"diff-a": 0.4, "diff-b": 0.4, "diff-c": 0.1}


def test_order_and_explicit_ties():
    rows = rank_candidates(_ConstScorer(SCORES), CANDS)
    assert rows[0].candidate_id == "c" and rows[0].rank == 1 and not rows[0].tie_group
    # a and b tie at 0.4: SAME rank, tie_group + break named
    tied = [r for r in rows if r.tie_group]
    assert {r.candidate_id for r in tied} == {"a", "b"}
    assert all(r.rank == 2 for r in tied)
    assert all(r.tie_break == "patch_sha256 ascending" for r in tied)
    # tie-break actually deterministic: sha( "diff-a" ) vs sha( "diff-b" ) order decides placement


def test_determinism_property_shuffled_inputs():
    """Same inputs, any submission order ⇒ identical output bytes (AC property)."""
    base = serialize_ordering(rank_candidates(_ConstScorer(SCORES), CANDS))
    rng = random.Random(7)
    for _ in range(25):
        shuffled = CANDS[:]
        rng.shuffle(shuffled)
        assert serialize_ordering(rank_candidates(_ConstScorer(SCORES), shuffled)) == base


def test_guards():
    with pytest.raises(SchemaError):
        rank_candidates(_ConstScorer({}), [{"id": "x", "patch_diff": "d"}])  # N<2
    with pytest.raises(SchemaError):  # duplicate ids
        rank_candidates(_ConstScorer({"d1": 0.1, "d2": 0.2}),
                        [{"id": "x", "patch_diff": "d1"}, {"id": "x", "patch_diff": "d2"}])
    with pytest.raises(SchemaError):  # scorer out of bounds
        rank_candidates(_ConstScorer({"d1": 1.5, "d2": 0.2}),
                        [{"id": "x", "patch_diff": "d1"}, {"id": "y", "patch_diff": "d2"}])
    with pytest.raises(SchemaError):  # non-text patch
        rank_candidates(_ConstScorer({}), [{"id": "x", "patch_diff": None},
                                           {"id": "y", "patch_diff": "d"}])


def test_distinct_scores_full_order():
    scores = {"d1": 0.9, "d2": 0.1, "d3": 0.5}
    rows = rank_candidates(_ConstScorer(scores),
                           [{"id": "a", "patch_diff": "d1"}, {"id": "b", "patch_diff": "d2"},
                            {"id": "c", "patch_diff": "d3"}])
    assert [r.candidate_id for r in rows] == ["b", "c", "a"]
    assert [r.rank for r in rows] == [1, 2, 3]
    assert all(not r.tie_group for r in rows)
