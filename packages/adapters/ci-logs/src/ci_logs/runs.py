"""Public CI run enumeration (GitHub Actions) + resumable cursor + pair deposits.

Edge-side only (AD-6): the network lives HERE, never in core. A harvest run:
1. enumerates workflow runs (paged, 100/page — the cheap part of the budget),
2. fetches the head-commit `.diff` (web endpoint, robots/throttle via Fetcher),
3. deposits patch + provenance v2 under data/landing/ci-logs/<repo>/<run_id>/,
4. advances an interrupt-safe cursor so a rerun is a zero-write no-op (AC 3).

The API enumeration JSON is intentionally NOT stored: the pair (patch bytes +
provenance) IS the deposit; enumeration pages are occurrence metadata (AD-7).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from core_schema.errors import SchemaError

from ci_logs.fetcher import Fetcher

GITHUB_API = "https://api.github.com"
GITHUB_WEB = "https://github.com"


@dataclass(frozen=True)
class Cursor:
    repo: str
    page: int
    last_run_id: int


@dataclass(frozen=True)
class HarvestResult:
    new_pairs: int
    enumerated: int
    manifest: dict


def save_cursor(path: Path, cursor: Cursor) -> None:
    """Atomic: tmp + rename — a crash never leaves a torn cursor (AC 3)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(cursor), indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def load_cursor(path: Path) -> Cursor | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
        return Cursor(repo=raw["repo"], page=int(raw["page"]), last_run_id=int(raw["last_run_id"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise SchemaError("LI-CILOG-002", "cursor file corrupt", {"path": str(path)}) from exc


def enumerate_runs(
    client: httpx.Client, repo: str, page: int = 1, api_base: str = GITHUB_API
) -> tuple[list[dict], bool]:
    """One page of workflow runs. Returns (runs, has_more)."""
    resp = client.get(f"{api_base}/repos/{repo}/actions/runs", params={"per_page": "100", "page": str(page)})
    resp.raise_for_status()
    runs = resp.json().get("workflow_runs", [])
    return runs, len(runs) == 100


def repo_license(client: httpx.Client, repo: str, api_base: str = GITHUB_API) -> str:
    """SPDX id or UNKNOWN — never guess (rights traceability, FR-15/policy)."""
    try:
        resp = client.get(f"{api_base}/repos/{repo}/license")
    except httpx.HTTPError:
        return "UNKNOWN"
    if resp.status_code != 200:
        return "UNKNOWN"
    return str((resp.json().get("license") or {}).get("spdx_id") or "UNKNOWN")


def harvest_repo(
    client: httpx.Client,
    fetcher: Fetcher,
    repo: str,
    landing_root: Path,
    *,
    max_pairs: int | None = None,
    api_base: str = GITHUB_API,
    web_base: str = GITHUB_WEB,
) -> HarvestResult:
    """One resumable window over a repo's public Actions runs."""
    source_dirname = repo.replace("/", "_per_")
    dest_root = landing_root / "ci-logs" / source_dirname
    cursor_path = dest_root / ".cursor.json"
    cursor = load_cursor(cursor_path)
    seen_from = cursor.last_run_id if cursor else None

    license_spdx = repo_license(client, repo, api_base)
    deposited: list[dict] = []
    enumerated = 0
    page = cursor.page if cursor else 1
    newest_seen = seen_from

    while True:
        runs, has_more = enumerate_runs(client, repo, page, api_base)
        if not runs:
            break
        for run in runs:
            run_id = int(run["id"])
            if seen_from is not None and run_id <= seen_from:
                has_more = False  # entered already-landed territory
                break
            enumerated += 1
            if max_pairs is not None and len(deposited) >= max_pairs:
                has_more = False
                break
            head_sha = run["head_sha"]
            pr = (run.get("pull_requests") or [{}])[0].get("number")
            res = fetcher.fetch(
                f"{web_base}/{repo}/commit/{head_sha}.diff",
                landing_root,
                f"ci-logs/{source_dirname}",
                str(run_id),
                extra_provenance={
                    "source": "github-actions",
                    "repo": repo,
                    "head_sha": head_sha,
                    "head_branch": run.get("head_branch"),
                    "event": run.get("event"),
                    "workflow_run_id": run_id,
                    "run_attempt": run.get("run_attempt", 1),
                    "run_conclusion": run.get("conclusion"),
                    "run_created_at": run.get("created_at"),
                    "pr_number": pr,
                    "license": license_spdx,
                },
            )
            deposited.append(
                {
                    "path": str(res.path.relative_to(landing_root)),
                    "sha256": res.sha256,
                    "bytes": res.path.stat().st_size,
                    "run_id": run_id,
                    "conclusion": run.get("conclusion"),
                }
            )
            newest_seen = run_id
        if not has_more:
            break
        page += 1

    if deposited:
        save_cursor(cursor_path, Cursor(repo=repo, page=page, last_run_id=int(newest_seen or 0)))
    elif cursor is None and enumerated == 0:
        save_cursor(cursor_path, Cursor(repo=repo, page=1, last_run_id=0))

    manifest = {
        "landing_manifest_version": 2,
        "origin": "ci-logs",
        "source_id": f"github-actions-{source_dirname}",
        "repo": repo,
        "license": license_spdx,
        "deposited": deposited,
        "enumerated": enumerated,
        "new_pairs": len(deposited),
    }
    dest_root.mkdir(parents=True, exist_ok=True)
    (dest_root / ".harvest-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return HarvestResult(new_pairs=len(deposited), enumerated=enumerated, manifest=manifest)
