"""Local predictor serving (story 5.2, AD-14): the pinned artifact predicts —
pure stdlib (murmur3 + sigmoid), zero ML dependency, zero network, zero LLM.

The artifact = a single pinned `predictor.json` (probe-predictor-v0 format):
{predictor_version, corpus_version, measured, vectorizer, model{intercept,
coefficients}}. Featurization mirrors sklearn HashingVectorizer(
n_features=2**12, alternate_sign=False, norm="l2", lowercase=True,
token_pattern=r"\\b\\w\\w+\\b") — bit-compat proven by test when the ml extra
exists. NO fallback: a malformed artifact refuses (LI-GATE-006), never guesses.
"""

from __future__ import annotations

import math
import re

from core_schema.errors import SchemaError

from gate._murmur3 import murmur3_32
from gate.ports import PinnedSnapshot

_TOKEN = re.compile(r"(?u)\b\w\w+\b")


def featurize(document: str, n_features: int = 2**12) -> list[float]:
    """The serving-side exact mirror of probe.embeddings' HashingVectorizer call."""
    if not isinstance(n_features, int) or n_features <= 0:
        raise SchemaError("LI-GATE-006", "n_features must be a positive int", {"got": n_features})
    counts: dict[int, float] = {}
    for tok in _TOKEN.findall(document.lower()):
        h = murmur3_32(tok.encode("utf-8"))
        signed = h - (1 << 32) if h >= (1 << 31) else h  # sklearn: mmh3 signed…
        col = abs(signed) % n_features  # …positive=True → abs(signed)
        counts[col] = counts.get(col, 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in counts.values()))
    if norm == 0.0:
        return []  # empty document → zero vector → sigmoid(prior) at score time
    vec = [0.0] * (max(counts) + 1)
    for col, v in counts.items():
        vec[col] = v / norm
    return vec


class PinnedPredictor:
    """The loaded, hash-verified serving object. Construct via `from_snapshot`."""

    def __init__(self, *, coefficients: list[float], intercept: float,
                 n_features: int, measured: dict, version: str) -> None:
        if len(coefficients) != n_features:
            raise SchemaError("LI-GATE-006", "coefficient count ≠ n_features", {})
        if not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c)
                   for c in coefficients):
            raise SchemaError("LI-GATE-006", "non-finite or bool coefficient", {})
        if isinstance(intercept, bool) or not math.isfinite(intercept):
            raise SchemaError("LI-GATE-006", "intercept not finite", {})
        self._w = coefficients
        self._b = intercept
        self._nf = n_features
        self.measured = measured
        self.predictor_version = version

    @classmethod
    def from_snapshot(cls, snap: PinnedSnapshot) -> PinnedPredictor:
        m = snap.manifest  # already the hash-pinned bytes' parse (ports job)
        vec = m.get("vectorizer")
        model = m.get("model")
        if not isinstance(vec, dict) or not isinstance(model, dict):
            raise SchemaError("LI-GATE-006", "predictor artifact sections malformed", {})
        # the serving mirror implements EXACTLY one recipe — the artifact must
        # declare it or be refused (a pin binds bytes, not recipe semantics):
        recipe = {"kind": "sklearn.HashingVectorizer", "alternate_sign": False,
                  "norm": "l2", "lowercase": True, "token_pattern": r"\b\w\w+\b"}
        for k, v in recipe.items():
            if vec.get(k) != v:
                raise SchemaError("LI-GATE-006", f"vectorizer recipe mismatch on {k}",
                                  {"expected": v, "got": vec.get(k)})
        nf_raw, ic_raw = vec.get("n_features"), model.get("intercept")
        coef = model.get("coefficients")
        if isinstance(nf_raw, bool) or isinstance(ic_raw, bool):
            raise SchemaError("LI-GATE-006", "bool where a number belongs", {})
        try:
            n_features = int(nf_raw)
            intercept = float(ic_raw)
        except (TypeError, ValueError, OverflowError) as exc:
            raise SchemaError("LI-GATE-006", "predictor artifact malformed", {}) from exc
        if not isinstance(coef, list):
            raise SchemaError("LI-GATE-006", "predictor coefficients malformed", {})
        try:
            coefs = [float(c) for c in coef]  # bools/finiteness refused by __init__
        except (TypeError, ValueError, OverflowError) as exc:
            raise SchemaError("LI-GATE-006", "predictor coefficients malformed", {}) from exc
        return cls(coefficients=coefs, intercept=intercept, n_features=n_features,
                   measured=m.get("measured") or {}, version=m.get("predictor_version"))

    def score(self, document: str) -> float:
        """logistic sigmoid over the hashed feature vector. Exact, deterministic."""
        vec = featurize(document, self._nf)
        z = self._b + sum(self._w[i] * v for i, v in enumerate(vec))
        # numerically stable sigmoid
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        ez = math.exp(z)
        return ez / (1.0 + ez)
