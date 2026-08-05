"""Clean slice assembly (Story 3.1): public metadata → hardened slice artifact.

Reads the landing items digests (public-corpora), applies the lite rejectors,
writes the clean slice repo-locally — and, when invoked with a store root, also
writes a reproducible store artifact named `clean-slice` with full disclosure
(accept/reject counts + criteria) per FR-16-lite.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from probe.hardening import filter_slice

SLICE_ARTIFACT_ID = "clean-slice"


@dataclass(frozen=True)
class SliceReport:
    total_in: int
    kept: int
    rejected: int
    reject_rate: float
    by_reason: dict[str, int]
    out_path: Path


def assemble_slice(
    items_path: Path,
    *,
    governance_root: Path,
    known_hackable: set[str] | None = None,
) -> SliceReport:
    items: list[dict[str, Any]] = json.loads(Path(items_path).read_text())
    kept, rejected = filter_slice(items, known_hackable=known_hackable)

    by_reason: dict[str, int] = {}
    for r in rejected:
        for reason in r.reason.split(","):
            by_reason[reason] = by_reason.get(reason, 0) + 1

    out_dir = governance_root / "probe-design" / "clean-slice"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "items.json"
    out_path.write_text(json.dumps(kept, indent=1, sort_keys=True) + "\n")

    disclosure = out_dir / "DISCLOSURE.md"
    rej = by_reason  # shorthand
    disclosure.write_text(
        "# Clean slice disclosure (FR-16 lite)\n\n"
        f"- input items: {len(items)}\n"
        f"- kept: {len(kept)}\n"
        f"- rejected: {len(rejected)} (rate: {len(rejected)/len(items):.2%})\n"
        f"- by reason: {rej}\n"
        f"- criteria document: probe/src/probe/hardening.py (rules named at top)\n"
    )
    total = len(items)
    rate = (len(rejected) / total) if total else 0.0
    return SliceReport(total, len(kept), len(rejected), rate, by_reason, out_path)
