"""On-disk contract constants for store-layout-v1. See store-layout-v1/README.md."""

from __future__ import annotations

from hashlib import sha256

LAYOUT_VERSION = "store-layout-v1"

# AD-7 classes: reproducible manifests must be content-only.
REPRODUCIBLE_CLASSES = frozenset(
    {
        "canonical-snapshot",
        "labels",
        "quarantine",
        "figure",
        "bundle",
        "arm-artifact",
        "prereg-commit",
        "release-manifest",
        "corpus-item-set",
        "corpus-release",
        "ranking-report",
    }
)

# Documented bootstrap identity: content hash of the empty canonical set.
EMPTY_STORE_VERSION = sha256(b"[]").hexdigest()
