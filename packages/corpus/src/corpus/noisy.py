"""Noisy-tier item assembly (core package: reads landing deposits — ZERO network, AD-6).

Canonical mapping (THE rule — cited by corpus README and every manifest):

- task of a noisy item = (repo_full_name, head commit sha, f2p_tests=()) — noisy
  items carry NO fail-to-pass list; the task fingerprint's test slot is the
  empty tuple. That is deliberate: the Noisy Tier is pretraining substrate, not
  measurement data (Epic-3 retro: measurement-grade flips stay the Clean Tier).
- attempt identity = core_schema.identity.attempt_id(task_id, sanitized patch,
  env fingerprint, run created_at) — the ONLY identity code (AD-12). Re-running
  a harvest window re-derives identical ids; cross-source duplicates collapse
  to one primary entry and are counted (FR-2).
- patch text is SANITIZED BEFORE hashing/storage (frozen patterns,
  governance/sanitize-policy.toml): the item never carries a raw secret, and
  identity/content stay consistent (the same bytes hash everywhere).
- environment is NOT observed for public CI: a single documented
  not-measured fingerprint constant is used; divergence risk noted.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from core_schema.domain import EnvironmentFingerprint
from core_schema.errors import SchemaError
from core_schema.identity import attempt_id, normalize_diff, task_fingerprint
from pydantic import BaseModel, ConfigDict
from traces_ingest.sanitize import sanitize_text

#: Documented stand-in: public-CI environments are not observed.
UNOBSERVED_ENV = EnvironmentFingerprint(
    os_family="gha-unobserved",
    python_version="unobserved",
    deps_lock_sha256="0" * 64,
)


class NoisyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str  # canonical attempt identity (AD-12 / FR-2)
    task_id: str  # (repo, head_sha, f2p=()) fingerprint
    repo: str
    head_sha: str
    workflow_run_id: int
    pr_number: int | None  # from provenance; drives the pr-level exclusion leg (4.2 CR)
    conclusion: str
    license: str
    attempt_start_utc: str
    patch_sha256: str  # of the SANITIZED patch text
    sanitize_counts: dict[str, int]
    provenance_path: str  # landing-relative, for lineage audits


class BuildResult(BaseModel):
    items: list[NoisyItem]
    duplicates: int
    excluded_rights: list[dict]  # audit queue: never enters a tier
    corrupt: int  # torn/degenerate deposits skipped, counted (P11) — never fatal
    scanned: int


def _parse_instant(raw: str | None, ctx: str) -> datetime:
    if not raw:  # both timestamps absent (P11): coded, never a bare TypeError
        raise SchemaError("LI-CORPUS-003", "missing run timestamp", {"ctx": ctx})
    try:
        dt = datetime.fromisoformat(raw)  # Python 3.11+ parses the Z suffix natively
    except ValueError as exc:
        raise SchemaError("LI-CORPUS-003", "unparseable run timestamp", {"ctx": ctx, "got": raw}) from exc
    if dt.tzinfo is None:
        raise SchemaError("LI-CORPUS-003", "naive run timestamp", {"ctx": ctx, "got": raw})
    return dt.astimezone(UTC)


def build_items(landing_root: Path, license_allowlist: list[str]) -> BuildResult:
    """Walk ci-logs deposits → deduped, sanitized, rights-filtered items."""
    ci_root = Path(landing_root) / "ci-logs"
    items: dict[str, NoisyItem] = {}
    duplicates = 0
    corrupt = 0
    excluded: list[dict] = []
    scanned = 0
    if not ci_root.is_dir():
        return BuildResult(items=[], duplicates=0, excluded_rights=[], corrupt=0, scanned=0)

    for prov_path in sorted(ci_root.glob("*/*/provenance.json")):
        run_dir = prov_path.parent
        patch_path = run_dir / "patch.diff"
        if not patch_path.is_file():
            continue  # log-only deposits are not pairs
        scanned += 1
        try:
            prov = json.loads(prov_path.read_text())
        except ValueError:
            corrupt += 1  # torn write (deposit order: patch, then provenance) — skip
            continue
        repo = prov.get("repo", "unknown/unknown")
        head_sha = prov.get("head_sha", "")
        license_spdx = prov.get("license", "UNKNOWN")
        if license_spdx not in license_allowlist:
            excluded.append(
                {"repo": repo, "run_id": prov.get("workflow_run_id"), "license": license_spdx}
            )
            continue
        sanitized = sanitize_text(patch_path.read_text(errors="replace"))
        text = normalize_diff(sanitized.text)
        start_raw = prov.get("run_created_at") or prov.get("fetched_at_utc")
        start = _parse_instant(start_raw, f"{repo}#{prov.get('workflow_run_id')}")
        tid = task_fingerprint(repo, head_sha, ())
        iid = attempt_id(tid, text, UNOBSERVED_ENV, start)
        item = NoisyItem(
            item_id=iid,
            task_id=tid,
            repo=repo,
            head_sha=head_sha,
            workflow_run_id=int(prov.get("workflow_run_id", 0)),
            pr_number=(int(pr_raw) if (pr_raw := prov.get("pr_number")) is not None else None),
            conclusion=str(prov.get("run_conclusion")),
            license=license_spdx,
            attempt_start_utc=start.isoformat().replace("+00:00", "Z"),
            patch_sha256=sha256(text.encode()).hexdigest(),
            sanitize_counts=sanitized.counts,
            provenance_path=str(prov_path.relative_to(landing_root)),
        )
        if iid in items:
            duplicates += 1  # same canonical attempt, another deposit — one primary
            continue
        items[iid] = item
    return BuildResult(
        items=list(items.values()), duplicates=duplicates, excluded_rights=excluded,
        corrupt=corrupt, scanned=scanned,
    )
