"""Feature rendering (OQ-2) + split manifests (FR-12). Deterministic, data-only.

One rendered input document per attempt: patch diff + task statement + failed-test
tail — nothing else. Hashing is by canonical content hash, documents-by-document.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any


def render_document(item: dict[str, Any]) -> str:
    """The ONLY place an attempt becomes text. Fixed schema; recorded in design."""
    parts = [
        "# PROBLEM STATEMENT",
        (item.get("problem_statement") or "")[:4000],
        "\n# PATCH DIFF",
        item.get("patch") or "",
        "\n# FAILED TESTS",
        "\n".join(item.get("FAIL_TO_PASS") or []),
    ]
    return "\n".join(parts)


def document_hash(doc: str) -> str:
    return sha256(doc.encode()).hexdigest()


def render_all(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Render every item; returns [{instance_id, document, document_hash}]."""
    return [
        {
            "instance_id": it["instance_id"],
            "repo": it.get("repo", ""),
            "document": render_document(it),
            "document_hash": document_hash(render_document(it)),
        }
        for it in items
    ]


def write_rendered(items: list[dict[str, Any]], out_path: Path) -> list[dict[str, str]]:
    rows = render_all(items)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n")
    return rows
