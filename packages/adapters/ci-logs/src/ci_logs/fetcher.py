"""CI-logs adapter, productionized (story 4.1): robots respect, per-host
throttling, and rate-limit-budget discipline.

- robots.txt: RFC 9309-ish (404 → allow; 5xx → block; other 4xx → allow; 2xx →
  parse). Robots fetches are throttled like any host traffic (politeness is
  about the host, full stop).
- Rate budget: 403/429 with an exhausted budget (`x-ratelimit-remaining: 0`)
  waits until `x-ratelimit-reset` and retries ONCE; a second refusal is a hard
  error (LI-CILOG-001) — never a hammer. Secondary limits honor `retry-after`
  when present.
- provenance v2 (see FetchResult.provenance): fetched_at, url, status,
  source_id, run_id, plus any caller-supplied extraction fields
  (repo/commits/workflow/license/robots disposition).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib import robotparser
from urllib.parse import urlparse

import httpx
from core_schema.errors import SchemaError


@dataclass(frozen=True)
class FetchResult:
    path: Path
    sha256: str
    provenance: dict


@dataclass
class _Budget:
    """Token-level GitHub budget state, fed by response headers."""

    remaining: int | None = None
    reset_epoch: int | None = None

    def update(self, headers: httpx.Headers) -> None:
        r = headers.get("x-ratelimit-remaining")
        t = headers.get("x-ratelimit-reset")
        if r is not None:
            self.remaining = int(r)
        if t is not None:
            self.reset_epoch = int(t)


@dataclass
class Fetcher:
    client: httpx.Client
    min_interval_s: float = 1.0
    sleeper: Any = time.sleep  # injectable for tests
    time_fn: Any = time.time  # injectable for tests (rate-limit reset windows)
    _last_by_host: dict[str, float] = field(default_factory=dict)
    _budget: _Budget = field(default_factory=_Budget)

    def fetch(
        self,
        url: str,
        dest_dir: Path,
        source_id: str,
        run_id: str,
        extra_provenance: dict | None = None,
    ) -> FetchResult:
        if not self._allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        resp = self._get_with_budget(url)
        return self._deposit(resp, url, dest_dir, source_id, run_id, extra_provenance)

    def _get_with_budget(self, url: str) -> httpx.Response:
        """One retry after a rate-limit refusal, then hard fail (LI-CILOG-001)."""
        for attempt in range(2):
            self._throttle(urlparse(url).netloc)
            resp = self.client.get(url, follow_redirects=True)
            self._budget.update(resp.headers)
            if resp.status_code in (403, 429) and self._budget.remaining == 0:
                if attempt == 0:
                    self._wait_for_reset(resp)
                    continue
                raise SchemaError(
                    "LI-CILOG-001",
                    "rate limit still exhausted after waiting for reset",
                    {"url": url},
                )
            resp.raise_for_status()
            return resp
        raise AssertionError("unreachable")

    def _wait_for_reset(self, resp: httpx.Response) -> None:
        retry_after = resp.headers.get("retry-after")
        if retry_after is not None:
            self.sleeper(max(float(retry_after), 1.0))
            return
        reset = self._budget.reset_epoch or 0
        self.sleeper(max(reset - int(self.time_fn()), 1))

    def _deposit(
        self,
        resp: httpx.Response,
        url: str,
        dest_dir: Path,
        source_id: str,
        run_id: str,
        extra: dict | None,
    ) -> FetchResult:
        out = dest_dir / source_id / str(run_id)
        out.mkdir(parents=True, exist_ok=True)
        content = resp.content
        name = "patch.diff" if url.endswith(".diff") else "log.txt"
        artifact = out / name
        artifact.write_bytes(content)
        prov: dict = {
            "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "url": url,
            "status": resp.status_code,
            "source_id": source_id,
            "run_id": str(run_id),
            "robots": "allow",
            "sha256_patch": sha256(content).hexdigest() if name == "patch.diff" else None,
        }
        prov = {k: v for k, v in prov.items() if v is not None}
        prov.update(extra or {})
        (out / "provenance.json").write_text(json.dumps(prov, indent=2, sort_keys=True))
        return FetchResult(artifact, sha256(content).hexdigest(), prov)

    def _throttle(self, host: str) -> None:
        now = time.monotonic()
        last = self._last_by_host.get(host, 0.0)
        delta = now - last
        if delta < self.min_interval_s:
            self.sleeper(self.min_interval_s - delta)
        self._last_by_host[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        """RFC 9309-ish: 404 → allow; 5xx → block; other 4xx → allow; 2xx → parse.
        The robots fetch itself is throttled like any host traffic."""
        host = urlparse(url).netloc
        self._throttle(host)
        resp = self.client.get(f"{self._origin(url)}/robots.txt", follow_redirects=True)
        if resp.status_code == 404:
            return True
        if resp.status_code >= 500:
            return False
        if resp.status_code >= 400:
            return True
        rp = robotparser.RobotFileParser()
        rp.parse(resp.text.splitlines())
        return rp.can_fetch("*", url)

    @staticmethod
    def _origin(url: str) -> str:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"
