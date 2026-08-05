"""Chain assembly — the ONLY place the AD-5 topology is built. Pure functions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class ChainManifest:
    release: str
    bundle: str
    snapshot: str
    ruleset: str
    code_commit: str
    chain_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "release": self.release,
            "bundle": self.bundle,
            "snapshot": self.snapshot,
            "ruleset": self.ruleset,
            "code_commit": self.code_commit,
            "chain_hash": self.chain_hash,
        }


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def assemble_chain(
    release_hash: str,
    bundle_hash: str,
    snapshot_hash: str,
    ruleset_hash: str,
    code_commit: str,
) -> ChainManifest:
    """Fixed AD-5 topology: release → bundle → snapshot → ruleset → commit."""
    body = {
        "release": release_hash,
        "bundle": bundle_hash,
        "snapshot": snapshot_hash,
        "ruleset": ruleset_hash,
        "code_commit": code_commit,
    }
    return ChainManifest(**body, chain_hash=sha256(_canon(body).encode()).hexdigest())


@dataclass(frozen=True)
class PrecedenceVerdict:
    status: Literal["ok", "violation", "skipped"]
    detail: str = ""


def _parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"naive timestamp in ledger: {s}")
    return dt.astimezone(timezone.utc)


def verify_chain_precedence(ledger_path: Path, manifests: list[dict]) -> PrecedenceVerdict:
    """Every label-set manifest's ruleset must be anchored BEFORE its run started.

    Ledger shape (jsonl): rows with {"type": "anchor", "ruleset_hash", "anchored_at"}
    and {"type": "run", "run_id", "started_at", "ruleset_hash"}. Only manifests whose
    artifact_type is "labels" are checked; others ignored.
    """
    anchors: dict[str, list[datetime]] = {}
    runs: dict[str, dict[str, Any]] = {}
    for line in Path(ledger_path).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("type") == "anchor":
            anchors.setdefault(row["ruleset_hash"], []).append(_parse_ts(row["anchored_at"]))
        elif row.get("type") == "run":
            runs[row["run_id"]] = row

    for man in manifests:
        if man.get("artifact_type") != "labels":
            continue
        inputs = man.get("inputs") or {}
        run_id = inputs.get("run_id")
        run = runs.get(run_id)
        if run is None:
            return PrecedenceVerdict("violation", f"label manifest {man.get('artifact_id', '?')} references unknown run_id {run_id}")
        ruleset_hash = run["ruleset_hash"]
        anchored = anchors.get(ruleset_hash, [])
        started = _parse_ts(run["started_at"])
        if not anchored:
            return PrecedenceVerdict("violation", f"ruleset {ruleset_hash[:12]}… never anchored")
        if min(anchored) > started:
            return PrecedenceVerdict("violation", f"ruleset anchored after the run started (anchored {min(anchored).isoformat()} > run {started.isoformat()})")
    return PrecedenceVerdict("ok")
