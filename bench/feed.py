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
    """Reads canonical snapshot PAYLOADS only (raw store files, AD-8).
    Manifests/META are never items; non-dict rows are contained as rejections
    would be — silently swallowing is what corrupts the mirror."""
    items: list[dict[str, Any]] = []
    skipped: list[str] = []
    for f in sorted(store_root.rglob("*.json")):
        name = f.name
        if name == "META.json" or name.endswith(".artifact.json") or ".staging" in f.parts:
            skipped.append(str(f.relative_to(store_root)))
            continue
        data = json.loads(f.read_text())
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            if not isinstance(row, dict):
                skipped.append(str(f.relative_to(store_root)))
                continue
            item = dict(row)
            item["dataset_item_id"] = row.get("attempt_id") or row.get("id") or str(
                f.relative_to(store_root)
            )
            items.append(item)
    if skipped:
        import logging

        logging.getLogger("bench.feed").warning("skipped non-payload files: %s", skipped)
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
