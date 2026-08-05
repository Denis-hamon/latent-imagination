"""bench feed: canonical store → ATIF-conform feed → Phoenix import.

Offline-testable: the Phoenix client is any object with `ingest(items: list[dict])`
— tests fake it; production uses the real importer. Idempotence rides on
dataset item id == attempt_id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class Importer(Protocol):
    def ingest(self, items: list[dict[str, Any]]) -> None: ...


@dataclass(frozen=True)
class FeedSummary:
    items: int
    dataset_fingerprint: str


def store_to_feed_items(store_root: Path) -> list[dict[str, Any]]:
    """Reads the canonical store (raw files only — AD-8) into feed dicts."""
    items: list[dict[str, Any]] = []
    for f in sorted(store_root.rglob("*.json")):
        data = json.loads(f.read_text())
        if isinstance(data, list):
            rows = data
        else:
            rows = [data]
        for row in rows:
            item = dict(row)
            item["dataset_item_id"] = row.get("attempt_id") or row.get("id") or f.name
            item["_source_file"] = str(f.relative_to(store_root))
            items.append(item)
    return items


def feed(importer: Importer, store_root: Path) -> FeedSummary:
    from hashlib import sha256

    items = store_to_feed_items(store_root)
    importer.ingest(items)
    canon = json.dumps(
        sorted(items, key=lambda r: r["dataset_item_id"]),
        sort_keys=True,
        separators=(",", ":"),
    )
    return FeedSummary(items=len(items), dataset_fingerprint=sha256(canon.encode()).hexdigest())
