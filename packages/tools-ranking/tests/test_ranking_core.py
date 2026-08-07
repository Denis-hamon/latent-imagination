"""Ranking core (story 8.1, FR-23): order, explicit ties, byte determinism."""

from __future__ import annotations

import random

import pytest
from core_schema.errors import SchemaError
from tools_ranking.core import TIE_BREAK_NAME, rank_candidates, serialize_ordering


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
    assert all(r.tie_break == TIE_BREAK_NAME for r in tied)
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


def test_duplicate_content_under_different_ids_stays_byte_deterministic():
    """CR 8.1 HIGH: identical patch text under two ids — tie chain ends on id."""
    scorer = _ConstScorer({"SAME": 0.5})
    a = {"id": "a", "patch_diff": "SAME"}
    b = {"id": "b", "patch_diff": "SAME"}
    c = {"id": "c", "patch_diff": "SAME"}
    base = serialize_ordering(rank_candidates(scorer, [a, b, c]))
    for perm in ([a, c, b], [b, a, c], [c, b, a]):
        assert serialize_ordering(rank_candidates(scorer, perm)) == base
    rows = rank_candidates(scorer, [b, a, c])
    assert [r.candidate_id for r in rows] == ["a", "b", "c"]  # id breaks the full tie
    assert all(r.tie_break == TIE_BREAK_NAME for r in rows)


def test_scorer_bool_or_garbage_coded():
    import pytest as pt
    from core_schema.errors import SchemaError as SE
    a, b = {"id": "a", "patch_diff": "x"}, {"id": "b", "patch_diff": "y"}
    with pt.raises(SE):
        rank_candidates(_ConstScorer({"x": True, "y": 0.3}), [a, b])
    with pt.raises(SE):
        rank_candidates(_ConstScorer({"x": float("nan"), "y": 0.3}), [a, b])
    with pt.raises(SE):

        class _Boom:
            def score(self, d):
                raise RuntimeError("nope")

        rank_candidates(_Boom(), [a, b])


def test_tie_break_order_is_actually_sha_then_id():
    scorer = _ConstScorer({"p": 0.5, "q": 0.5})
    rows = rank_candidates(scorer, [{"id": "z", "patch_diff": "q"}, {"id": "y", "patch_diff": "p"}])
    shas = [r.patch_sha256 for r in rows]
    assert shas == sorted(shas)  # intra-bucket sha ascending, asserted for real


def test_empty_patch_and_non_dict_coded():
    import pytest as pt
    from core_schema.errors import SchemaError as SE
    with pt.raises(SE):
        rank_candidates(_ConstScorer({}), [{"id": "a", "patch_diff": "  "},
                                           {"id": "b", "patch_diff": "y"}])
    with pt.raises(SE):
        rank_candidates(_ConstScorer({}), [None, {"id": "b", "patch_diff": "y"}])
