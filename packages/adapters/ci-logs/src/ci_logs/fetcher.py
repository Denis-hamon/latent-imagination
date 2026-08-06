"""CI-logs adapter, productionized (story 4.1 + review P2/P15/P16): robots
respect, per-host throttling, and ONE rate-limit-disciplined GET used by every
call in this package (web diffs AND api.github.com enumeration alike).

- robots.txt: RFC 9309-ish (404 → allow; 5xx → block; other 4xx → allow; 2xx →
  parse). Robots fetches are throttled like any host traffic.
- Rate budget (policy harvest-policy-v1, committed): 403/429 waits and retries
  — `retry-after` honored whenever present (numeric seconds or RFC HTTP-date),
  else wait to `x-ratelimit-reset` when the primary budget reads exhausted,
  else the registered exponential chain 60s·2ⁿ with n ≤ 5 attempts; after that
  a hard LI-CILOG-001 — never a hammer. Header parsing is defensive: malformed
  headers are ignored, never fatal.
- provenance v2: fetched_at, url, status, source_id, run_id, robots
  disposition, content hash, plus caller-supplied fields.
"""

from __future__ import annotations

import email.utils
import json
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib import robotparser
from urllib.parse import urlparse

import httpx
from core_schema.errors import SchemaError

_MAX_ATTEMPTS = 5  # policy: backoff 60s·2ⁿ, n ≤ 5, then hard failure


@dataclass(frozen=True)
class FetchResult:
    path: Path
    sha256: str
    provenance: dict


def _parse_int_header(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None  # malformed intermediaries are noise, not a crash (P15)


class Fetcher:
    """Robots/throttle/budget-disciplined getter. `sleeper` and `time_fn` are
    injectable for tests (no real sleeping in the suite)."""

    def __init__(
        self,
        client: httpx.Client,
        min_interval_s: float = 1.0,
        sleeper: Any = time.sleep,
        time_fn: Any = time.time,
    ) -> None:
        self._client = client
        self.min_interval_s = min_interval_s
        self._sleeper = sleeper
        self._time_fn = time_fn
        self._last_by_host: dict[str, float] = {}

    # ----- public surface -------------------------------------------------

    def api_get(
        self, url: str, params: dict | None = None, allow_status: frozenset[int] = frozenset()
    ) -> httpx.Response:
        """The ONE budget-disciplined GET. Every request of this package goes
        through here (P2) — REST enumeration, license lookup, and web diffs.
        `allow_status` whitelists statuses the caller wants to inspect itself
        (e.g. a 404 license lookup means "no license file", not an error)."""
        for attempt in range(_MAX_ATTEMPTS):
            self._throttle(urlparse(url).netloc)
            resp = self._client.get(url, params=params, follow_redirects=True)
            if resp.status_code not in (403, 429):
                if resp.status_code not in allow_status:
                    resp.raise_for_status()
                return resp
            if attempt == _MAX_ATTEMPTS - 1:
                raise SchemaError(
                    "LI-CILOG-001",
                    "rate limit persists after the registered backoff chain",
                    {"url": url, "attempts": attempt + 1},
                )
            self._wait(resp, attempt)
        raise AssertionError("unreachable")

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
        resp = self.api_get(url)
        return self._deposit(resp, url, dest_dir, source_id, run_id, extra_provenance)

    # ----- internals --------------------------------------------------------

    def _wait(self, resp: httpx.Response, attempt: int) -> None:
        retry_after = resp.headers.get("retry-after")
        if retry_after is not None:
            seconds = self._retry_after_seconds(retry_after)
            if seconds is not None:
                self._sleeper(max(seconds, 1.0))
                return
        remaining = _parse_int_header(resp.headers.get("x-ratelimit-remaining"))
        reset = _parse_int_header(resp.headers.get("x-ratelimit-reset"))
        if remaining == 0 and reset is not None:
            self._sleeper(max(reset - int(self._time_fn()), 1))
            return
        self._sleeper(float(60 * (2 ** attempt)))  # registered secondary backoff

    def _retry_after_seconds(self, value: str) -> float | None:
        try:
            return float(value)
        except ValueError:
            pass
        try:  # RFC 7231 allows an HTTP-date form
            dt = email.utils.parsedate_to_datetime(value)
            return dt.timestamp() - self._time_fn()
        except (TypeError, ValueError):
            return None

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
        # name from the parsed path, not the raw URL — query strings must not
        # re-type a patch as a log (P16)
        name = "patch.diff" if urlparse(url).path.endswith(".diff") else "log.txt"
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
            self._sleeper(self.min_interval_s - delta)
        self._last_by_host[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        """RFC 9309-ish: 404 → allow; 5xx → block; other 4xx → allow; 2xx → parse.
        The robots fetch itself is throttled like any host traffic."""
        host = urlparse(url).netloc
        self._throttle(host)
        resp = self._client.get(f"{self._origin(url)}/robots.txt", follow_redirects=True)
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
