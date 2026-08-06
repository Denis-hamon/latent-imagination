"""The REAL registry file is CI-checked (story 4.1, Task 3): it must parse via
store.registry at all times, and the real public-CI entry must be present with
a snapshot hash that means something (empty-set bootstrap constant)."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from store.registry import OriginClass, load_registry

REAL = Path(__file__).resolve().parents[3] / "data" / "registries" / "sources.yaml"
EMPTY_SET_HASH = sha256(b"[]").hexdigest()  # mirrors store/layout.EMPTY_STORE_VERSION


def test_real_registry_loads_and_carries_the_ci_entry():
    reg = load_registry(REAL)
    entry = reg["github-actions-public-ci"]
    assert entry.origin_class is OriginClass.PUBLIC_CI_LOGS
    assert entry.source_version == 1
    assert entry.snapshot_content_hash == EMPTY_SET_HASH  # pre-first-harvest state
    assert "harvest-policy-v1" in entry.notes


def test_real_registry_has_no_duplicate_ids():
    reg = load_registry(REAL)
    raw = [s["source_id"] for s in __import__("yaml").safe_load(REAL.read_text())["sources"]]
    assert len(raw) == len(reg)  # load_registry would raise on dupes; belt+braces
