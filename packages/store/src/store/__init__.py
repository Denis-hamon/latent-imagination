"""packages/store public surface. Thin by design (AD-8)."""

from store.emit import (
    WRITERS,
    StoreWriteError,
    WrittenArtifact,
    compute_store_version,
    write_artifact,
)
from store.layout import EMPTY_STORE_VERSION, LAYOUT_VERSION, REPRODUCIBLE_CLASSES
from store.validate import ValidationReport, validate_store

__all__ = [
    "EMPTY_STORE_VERSION",
    "LAYOUT_VERSION",
    "REPRODUCIBLE_CLASSES",
    "WRITERS",
    "StoreWriteError",
    "ValidationReport",
    "WrittenArtifact",
    "compute_store_version",
    "validate_store",
    "write_artifact",
]
