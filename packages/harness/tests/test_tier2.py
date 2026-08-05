"""Tier-2 kit divergence comparator tests."""

from __future__ import annotations

from harness.tier2 import compare_within_tolerance


def test_within_inclusive():
    r = compare_within_tolerance("erbve", 0.50, 0.52)
    assert r.within
    assert r.delta_pp == 2.0  # exactly on the boundary: INCLUDED (inclusive rule)


def test_outside():
    r = compare_within_tolerance("erbve", 0.50, 0.521)
    assert not r.within


def test_boundary_above_is_out():
    r = compare_within_tolerance("erbve", 0.50, 0.520001)
    assert not r.within
