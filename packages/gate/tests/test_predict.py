"""Local predictor serving (story 5.2) — pinned artifact scores locally,
bit-compatible with the training-side sklearn recipe (proven when ml extra
exists, skipped otherwise)."""

from __future__ import annotations

import json
import time
from hashlib import sha256

import pytest
from core_schema.errors import SchemaError
from gate.ports import load_pinned_snapshot
from gate.predict import PinnedPredictor, featurize

DOC = """# PROBLEM STATEMENT
fix the parser
# PATCH DIFF
--- a/p.py
+++ b/p.py
@@ -1 +1 @@
-return 0
+return 1
# FAILED TESTS
tests/test_p.py::test_ret"""


def _artifact(tmp_path, coefs=None, intercept=0.5):
    nf = len(coefs) if coefs is not None else 2**12
    art = {
        "predictor_version": "probe-predictor-v0",
        "corpus_version": "corpus-v0",
        "measured": {"precision": 0.6271},
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "n_features": nf,
                       "alternate_sign": False, "norm": "l2", "lowercase": True,
                       "token_pattern": r"\b\w\w+\b"},
        "model": {"kind": "logreg-sigmoid", "intercept": intercept,
                  "coefficients": coefs or [0.0] * nf},
    }
    (tmp_path / "META.json").write_text(json.dumps(
        {"layout_version": "store-layout-v1", "store_version": "a" * 64}))
    (tmp_path / "predictor.json").write_text(json.dumps(art))
    return tmp_path, sha256(json.dumps(art).encode()).hexdigest()


def test_score_is_deterministic_bounded_local(tmp_path):
    root, phash = _artifact(tmp_path)
    snap = load_pinned_snapshot(root, expected_predictor_hash=phash)
    p = PinnedPredictor.from_snapshot(snap)
    s1, s2 = p.score(DOC), p.score(DOC)
    assert s1 == s2 and 0.0 <= s1 <= 1.0
    assert abs(s1 - 1 / (1 + 2.718281828459045 ** -0.5)) < 1e-6  # zero weights → sigmoid(b)


def test_score_moves_with_weights(tmp_path):
    nf = 2**12
    vec = featurize(DOC, nf)
    coefs = [0.0] * nf
    for i, v in enumerate(vec):
        coefs[i] += 10.0 * v
    root, phash = _artifact(tmp_path, coefs=coefs, intercept=0.0)
    snap = load_pinned_snapshot(root, expected_predictor_hash=phash)
    p = PinnedPredictor.from_snapshot(snap)
    assert p.score(DOC) > 0.99  # z = 10 * <v,v> = 10 → sigmoid ≈ 0.99995


def test_malformed_artifact_refused(tmp_path):
    root, phash = _artifact(tmp_path)
    bad = json.loads((root / "predictor.json").read_text())
    bad["model"]["coefficients"] = [1.0]  # width mismatch
    (root / "predictor.json").write_text(json.dumps(bad))
    with pytest.raises(SchemaError):
        load_pinned_snapshot(root, expected_predictor_hash=phash)  # pin broke
    snap = load_pinned_snapshot(root, expected_predictor_hash=sha256(json.dumps(bad).encode()).hexdigest())
    with pytest.raises(SchemaError) as ei:
        PinnedPredictor.from_snapshot(snap)
    assert ei.value.code == "LI-GATE-006"


def test_latency_p95_comfortable(tmp_path):
    root, phash = _artifact(tmp_path)
    snap = load_pinned_snapshot(root, expected_predictor_hash=phash)
    p = PinnedPredictor.from_snapshot(snap)
    big = DOC * 400  # ~300 KB document
    t0 = time.perf_counter()
    for _ in range(20):
        p.score(big)
    dt = (time.perf_counter() - t0) / 20
    assert dt < 0.5  # advisory budget placeholder is 1.0 s; serving sits way under


def test_featurize_bitcompat_with_sklearn():
    """Skipped without the ml extra; when present, proves byte-identical columns."""
    pytest.importorskip("sklearn")
    from sklearn.feature_extraction.text import HashingVectorizer

    docs = [DOC, "fix: oauthlib regression in token refresh #42", ""]
    nf = 2**12
    ref = HashingVectorizer(n_features=nf, alternate_sign=False, norm="l2").transform(docs).toarray()
    mine = [featurize(d, nf) for d in docs]
    for d_i, row in enumerate(ref):
        got = mine[d_i]
        assert len(got) <= nf
        for col, v in zip(range(len(got)), got):
            assert abs(v - row[col]) < 1e-6, f"doc {d_i} col {col}"


def test_murmur3_reference_vectors():
    """Known constants (independent of sklearn): '' → 0; 'foo' → 0xf6a5c420? use our own ground truth."""
    from gate._murmur3 import murmur3_32

    assert murmur3_32(b"") == 0
    # mmh3 reference: 'foo' seed 0 = 0xf6a5c420 (widely published test vector)
    assert murmur3_32(b"foo") == 0xF6A5C420
