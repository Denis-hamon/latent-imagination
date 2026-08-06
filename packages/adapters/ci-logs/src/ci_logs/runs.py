"""Public CI run harvest (GitHub Actions) — resumable, idempotent, budget-capped.

Idempotency by construction (review P1): the deposit DIRECTORY (`<run_id>/` with
patch+provenance) is the membership index — a run whose directory exists is
never re-fetched or rewritten, whatever order GitHub returns (newest-first).
Enumeration always starts at page 1 (the head is where NEW runs appear); a full
page of already-known ids ends the sweep early. `max_pairs` just stops: the
page remainder's directories don't exist yet, so the next window picks it up.

Budgets (policy pre-registration made mechanical, P5): every request counts —
REST enumeration/license against `rest_requests_per_day`, diff fetches against
`max_diff_fetches_per_repo_day` — in a day-bucketed `.budget.json`. Hitting a
cap STOPS the harvest and discloses it in the manifest (never silent, R10).

All network via `Fetcher.api_get` (the single budget-disciplined GET, P2).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core_schema.errors import SchemaError

from ci_logs.fetcher import Fetcher

GITHUB_API = "https://api.github.com"
GITHUB_WEB = "https://github.com"
REGISTRY_SOURCE_ID = "github-actions-public-ci"  # the FR-1 registry key (P18)


def repo_dirname(repo: str) -> str:
    """Injective encoding (P8): escape '_' then join with '-'.

    `a_b/c` → `a__b-c`, `a/b_c` → `a-b__c` — distinct, reversible.
    """
    return repo.replace("_", "__").replace("/", "-")


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
    """Atomic: tmp + rename — a crash never leaves a torn cursor."""
    path.parent.mkdir(parents=True, exist_ok=True)  # P3: empty repo must not crash
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(cursor), indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def load_cursor(path: Path, repo: str) -> Cursor | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
        cur = Cursor(repo=raw["repo"], page=int(raw["page"]), last_run_id=int(raw["last_run_id"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise SchemaError("LI-CILOG-002", "cursor file corrupt", {"path": str(path)}) from exc
    if cur.repo != repo:  # P8: a colliding dirname must fail loud, never interleave
        raise SchemaError(
            "LI-CILOG-002", "cursor belongs to another repo", {"path": str(path), "cursor_repo": cur.repo}
        )
    return cur


@dataclass
class _Budget:
    """Day-bucketed counters persisted next to the cursor (P5)."""

    path: Path
    day: str = ""
    rest_requests: int = 0
    diff_fetches: int = 0
    stopped: str | None = field(default=None, repr=False)

    def _roll(self) -> None:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if self.day != today:
            self.day, self.rest_requests, self.diff_fetches = today, 0, 0
            self.stopped = None

    def count_rest(self, n: int = 1) -> None:
        self._roll()
        self.rest_requests += n

    def count_diff(self, n: int = 1) -> None:
        self._roll()
        self.diff_fetches += n

    def over(self, rest_cap: int, diff_cap: int) -> str | None:
        self._roll()
        if self.rest_requests >= rest_cap:
            self.stopped = f"rest_requests {self.rest_requests} >= cap {rest_cap}"
        elif self.diff_fetches >= diff_cap:
            self.stopped = f"diff_fetches {self.diff_fetches} >= cap {diff_cap}"
        return self.stopped

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(
            {"day": self.day, "rest_requests": self.rest_requests,
             "diff_fetches": self.diff_fetches, "stopped": self.stopped},
            indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.path)

    @classmethod
    def load(cls, path: Path) -> _Budget:
        b = cls(path=path)
        if path.exists():
            try:
                raw = json.loads(path.read_text())
                b.day, b.rest_requests = raw["day"], int(raw["rest_requests"])
                b.diff_fetches, b.stopped = int(raw["diff_fetches"]), raw.get("stopped")
            except (ValueError, KeyError, TypeError) as exc:
                raise SchemaError("LI-CILOG-002", "budget file corrupt", {"path": str(path)}) from exc
        b._roll()
        return b


def enumerate_runs(fetcher: Fetcher, repo: str, page: int, api_base: str) -> tuple[list[dict], bool]:
    """One page via the policed GET (P2). Returns (runs, has_more)."""
    resp = fetcher.api_get(
        f"{api_base}/repos/{repo}/actions/runs", params={"per_page": "100", "page": str(page)}
    )
    runs = resp.json().get("workflow_runs", [])
    return runs, len(runs) == 100


def repo_license(fetcher: Fetcher, repo: str, api_base: str) -> str:
    """SPDX id; UNKNOWN only on a genuine 404 (no license file). A transient
    failure aborts instead of audit-queueing the whole repo (P10)."""
    resp = fetcher.api_get(f"{api_base}/repos/{repo}/license", allow_status=frozenset({404}))
    if resp.status_code == 404:
        return "UNKNOWN"
    return str((resp.json().get("license") or {}).get("spdx_id") or "UNKNOWN")


def _base_sha(fetcher: Fetcher, repo: str, pr_number: int | None, api_base: str) -> str | None:
    """P4: the PR base sha when the run is a PR (one counted request); null for
    push events. Identity of the task stays on head_sha (dedup equivalence: the
    patch + window carry attempt identity) — the deviation is recorded."""
    if pr_number is None:
        return None
    resp = fetcher.api_get(f"{api_base}/repos/{repo}/pulls/{pr_number}", allow_status=frozenset({404}))
    if resp.status_code == 200:
        return (resp.json().get("base") or {}).get("sha")
    return None


def harvest_repo(
    fetcher: Fetcher,
    repo: str,
    landing_root: Path,
    policy,
    *,
    max_pairs: int | None = None,
    api_base: str = GITHUB_API,
    web_base: str = GITHUB_WEB,
) -> HarvestResult:
    """One resumable, budget-capped window over a repo's public Actions runs."""
    dirname = repo_dirname(repo)
    dest_root = landing_root / "ci-logs" / dirname
    cursor_path = dest_root / ".cursor.json"
    cursor = load_cursor(cursor_path, repo)
    budget = _Budget.load(dest_root / ".budget.json")

    license_spdx = None
    deposited: list[dict] = []
    enumerated = 0
    max_seen = cursor.last_run_id if cursor else 0

    page = 1
    while True:
        stop = budget.over(policy.budget.rest_requests_per_day, policy.budget.max_diff_fetches_per_repo_day)
        if stop or (max_pairs is not None and len(deposited) >= max_pairs):
            break
        budget.count_rest()  # enumeration page
        runs, has_more = enumerate_runs(fetcher, repo, page, api_base)
        enumerated += len(runs)
        if not runs:
            break
        known_streak = 0
        for run in runs:
            run_id = int(run["id"])
            max_seen = max(max_seen, run_id)
            if (dest_root / str(run_id) / "patch.diff").exists():
                known_streak += 1  # already landed — zero fetch, zero write (P1)
                continue
            known_streak = 0
            if run.get("conclusion") is None:
                continue  # P9: in-progress/queued runs land once they conclude
            stop = budget.over(policy.budget.rest_requests_per_day, policy.budget.max_diff_fetches_per_repo_day)
            if stop or (max_pairs is not None and len(deposited) >= max_pairs):
                break
            if license_spdx is None:
                budget.count_rest()
                license_spdx = repo_license(fetcher, repo, api_base)
            pr = (run.get("pull_requests") or [{}])[0].get("number")
            base_sha = None
            if pr is not None:
                budget.count_rest()
                base_sha = _base_sha(fetcher, repo, pr, api_base)
            budget.count_diff()
            res = fetcher.fetch(
                f"{web_base}/{repo}/commit/{run['head_sha']}.diff",
                landing_root,
                f"ci-logs/{dirname}",
                str(run_id),
                extra_provenance={
                    "registry_source_id": REGISTRY_SOURCE_ID,
                    "source": "github-actions",
                    "repo": repo,
                    "head_sha": run["head_sha"],
                    "base_sha": base_sha,
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
            deposited.append({
                "path": str(res.path.relative_to(landing_root)),
                "sha256": res.sha256,
                "bytes": res.path.stat().st_size,
                "run_id": run_id,
                "conclusion": run.get("conclusion"),
            })
        if not has_more or known_streak >= len(runs):
            break
        page += 1

    budget.save()
    save_cursor(cursor_path, Cursor(repo=repo, page=page, last_run_id=max_seen))

    # merge-append + atomic (P12): the manifest never loses prior deposits
    manifest_path = dest_root / ".harvest-manifest.json"
    prior: list[dict] = []
    if manifest_path.exists():
        try:
            prior = json.loads(manifest_path.read_text()).get("deposited", [])
        except ValueError:
            prior = []
    known = {d["run_id"] for d in prior}
    merged = prior + [d for d in deposited if d["run_id"] not in known]
    manifest = {
        "landing_manifest_version": 2,
        "origin": "ci-logs",
        "registry_source_id": REGISTRY_SOURCE_ID,
        "source_id": f"github-actions-{dirname}",
        "repo": repo,
        "license": license_spdx,
        "deposited": merged,
        "enumerated": enumerated,
        "new_pairs": len(deposited),
        "budget": {"day": budget.day, "rest_requests": budget.rest_requests,
                   "diff_fetches": budget.diff_fetches, "stopped": budget.stopped},
    }
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, manifest_path)
    return HarvestResult(new_pairs=len(deposited), enumerated=enumerated, manifest=manifest)
