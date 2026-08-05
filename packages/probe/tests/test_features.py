"""3.3: features render, repo-grouped splits, embedding extraction tests."""

from __future__ import annotations

from probe.features import render_document, write_rendered
from probe.splits import repo_grouped_split


def _items(n=20):
    repos = ["django/django", "scikit-learn/scikit-learn", "sympy/sympy", "astropy/astropy"]
    return [
        {
            "instance_id": f"i-{i}",
            "repo": repos[i % len(repos)],
            "problem_statement": f"problem {i}",
            "patch": f"--- a/src/x.py\n+++ b/src/x.py\n@@ -{i},1 +{i},1 @@\n-x\n+y\n",
            "FAIL_TO_PASS": [f"pkg/tests/test_{i}.py::test_x"],
        }
        for i in range(n)
    ]


def test_render_document_fixed_schema():
    doc = render_document(_items(1)[0])
    for marker in ("# PROBLEM STATEMENT", "# PATCH DIFF", "# FAILED TESTS"):
        assert marker in doc


def test_split_groups_by_repo():
    items = _items(40)
    m = repo_grouped_split(items, eval_frac=0.25, seed=42)
    train = set(m["train_instance_ids"])
    eval_ = set(m["eval_instance_ids"])
    assert not (train & eval_)
    # repo-grouped: a repo is either entirely in or entirely out of eval
    by_repo = {}
    for it in items:
        by_repo.setdefault(it["repo"], set()).add(it["instance_id"])
    for ids in by_repo.values():
        assert ids.issubset(train) or ids.issubset(eval_)
    # deterministic
    m2 = repo_grouped_split(items, eval_frac=0.25, seed=42)
    assert m["hash"] == m2["hash"]


def test_render_write_and_hash(tmp_path):
    rows = write_rendered(_items(3), tmp_path / "rendered.json")
    assert len(rows) == 3
    readback = (tmp_path / "rendered.json").read_text()
    assert '"document_hash"' in readback
