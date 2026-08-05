"""bench feed: idempotence + path coverage — with a fake importer (offline)."""

from __future__ import annotations

import json
from pathlib import Path

from bench.feed import feed, store_to_feed_items


class FakeImporter:
    def __init__(self):
        self.calls = []

    def ingest(self, items):
        self.calls.append(list(items))


def _store(tmp_path: Path) -> Path:
    root = tmp_path / "store"
    d = root / "canonical" / "snap-1" / "v0"
    d.mkdir(parents=True)
    (d / "snap.json").write_text(json.dumps([
        {"attempt_id": "a" * 64, "x": 1},
        {"attempt_id": "b" * 64, "x": 2},
    ]))
    return root


def test_items_use_attempt_id_as_identity(tmp_path):
    items = store_to_feed_items(_store(tmp_path))
    assert {i["dataset_item_id"] for i in items} == {"a" * 64, "b" * 64}


def test_two_feeds_identical_fingerprint(tmp_path):
    root = _store(tmp_path)
    s1 = feed(FakeImporter(), root)
    s2 = feed(FakeImporter(), root)
    assert s1.dataset_fingerprint == s2.dataset_fingerprint
