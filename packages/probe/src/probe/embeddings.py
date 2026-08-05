"""Frozen embedding extraction — baseline substrate.

The baseline arm's feature extractor is HashingVectorizer: stateless, deterministic,
no model download, CPU-only. sklearn is inside probe[ml] extras (AD-11) — importing
this module without the extra raises a clear error.
"""

from __future__ import annotations

from typing import Any


class MissingMLExtra(Exception):
    pass


def _load():
    try:
        import numpy as np  # noqa: F401
        from sklearn.feature_extraction.text import HashingVectorizer  # noqa: F401
    except ImportError as e:
        raise MissingMLExtra(
            "install the probe[ml] extra for embedding/training work: "
            "uv sync --locked --all-packages -P probe --extra ml"
        ) from e


def embed_documents(documents: list[str], n_features: int = 2**12) -> Any:
    """Frozen feature extraction. Version-agnostic because the vectorizer is
    stateless (character-free deterministic feature hashing)."""
    _load()
    import numpy as np
    from sklearn.feature_extraction.text import HashingVectorizer

    vec = HashingVectorizer(n_features=n_features, alternate_sign=False, norm="l2")
    X = vec.transform(documents)
    return X.toarray().astype(np.float32)
