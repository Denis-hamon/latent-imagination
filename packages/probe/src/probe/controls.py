"""FR-14 stylistic controls: strata-bucketed evaluation, not vibes.

Buckets (renderer-visible, no instance content needed):
- diff length strata (lines): the richest provenance marker
Which corpus an item came from is ALSO disclosed; we never pretend they interleave.
"""

from __future__ import annotations


def strata_key(diff_text: str) -> str:
    n = max(1, sum(1 for line in diff_text.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))))
    if n <= 5:
        return "tiny(1-5)"
    if n <= 20:
        return "small(6-20)"
    if n <= 80:
        return "medium(21-80)"
    return "large(81+)"


def stratified_precision(labels_rows_pred):
    """labels_rows_pred: iterable of (label:int, pred:int, patch:str, source:str).
    Counts TN too — a control that is silent on them is mutilated."""
    from collections import defaultdict

    by = defaultdict(lambda: [0, 0, 0, 0])  # tp, fp, fn, tn
    per_corpus = defaultdict(lambda: [0, 0, 0, 0])
    for label, pred, patch, source in labels_rows_pred:
        for book in (by[strata_key(patch)], per_corpus[source]):
            if pred == 1 and label == 1:
                book[0] += 1
            elif pred == 1 and label == 0:
                book[1] += 1
            elif pred == 0 and label == 1:
                book[2] += 1
            else:
                book[3] += 1

    def p(t):
        tp, fp, fn, tn = t
        return tp / (tp + fp) if (tp + fp) else None

    def tnr(t):
        tp, fp, fn, tn = t
        return tn / (tn + fp) if (tn + fp) else None

    return {
        "by_diff_length": {
            k: {"precision": p(v), "tnr": tnr(v), "tp": v[0], "fp": v[1], "fn": v[2], "tn": v[3]}
            for k, v in sorted(by.items())
        },
        "by_corpus": {
            k: {"precision": p(v), "tnr": tnr(v), "tp": v[0], "fp": v[1], "fn": v[2], "tn": v[3]}
            for k, v in sorted(per_corpus.items())
        },
    }
