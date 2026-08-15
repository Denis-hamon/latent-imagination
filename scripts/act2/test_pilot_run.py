"""Act II pilot run harness — extraction semantics (successor of the retired
test_pilot_harness.py, which tested the superseded pilot_harness.py module).

`advisory_score`/`pilot_tasks` no longer exist after the mac-model/node-eval
split (commit e7651f3); `extract_diff` survived in pilot_run.py with the same
contract — covered here, plus the sanitized variant (S14 sanitize-fix lineage).
"""

from __future__ import annotations

from scripts.act2.pilot_run import extract_diff, extract_diff_sanitized


def test_extract_diff_handles_fenced_and_bare():
    assert extract_diff("```diff\ndiff --git a/x b/x\n+1\n```") == "diff --git a/x b/x\n+1\n"
    assert extract_diff("some prose\ndiff --git a/y b/y\n+2\n") == "diff --git a/y b/y\n+2\n"
    assert extract_diff("no patch here") is None


def test_extract_diff_closure_only_fallback():
    # models that omit 'diff --git': ---/+++ + @@ is accepted
    text = "prose\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-x\n+y\n"
    assert extract_diff(text) is not None
    # but a lone --- without a hunk is not a diff
    assert extract_diff("prose\n--- a/f.py\njust words") is None


def test_extract_diff_sanitized_empty_becomes_none():
    assert extract_diff_sanitized("```diff\n```") is None
    assert extract_diff_sanitized("no patch") is None
