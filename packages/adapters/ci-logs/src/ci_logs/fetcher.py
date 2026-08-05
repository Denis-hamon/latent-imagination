"""CI-logs spike adapter: fetch public CI logs with real robots handling.

Parser = urllib.robotparser (stdlib, RFC 9309-ish): per-Host rules cached,
5xx → block, 404 → allow, redirects followed. All outbound requests throttled
per host, robots.txt fetches included (politeness is about the host, full stop).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class FetchResult:
    path: Path
    sha256: str
    provenance: dict


class Fetcher:
    def __init__(self, client: httpx.Client, min_interval_s: float = 1.0):
        self._client = client
        self._min_interval = min_interval_s
        self._last_by_host: dict[str, float] = {}

    def fetch(self, url: str, dest_dir: Path, source_id: str, run_id: str) -> FetchResult:
        host = urlparse(url).netloc
        if not self._allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        self._throttle(host)
        resp = self._client.get(url, follow_redirects=True)
        resp.raise_for_status()
        out = dest_dir / source_id / run_id
        out.mkdir(parents=True, exist_ok=True)
        log_path = out / "log.txt"
        log_path.write_bytes(resp.content)
        prov = {
            "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "url": url,
            "status": resp.status_code,
            "source_id": source_id,
            "run_id": run_id,
        }
        (out / "provenance.json").write_text(json.dumps(prov, indent=2, sort_keys=True))
        return FetchResult(log_path, sha256(resp.content).hexdigest(), prov)

    def _throttle(self, host: str) -> None:
        now = time.monotonic()
        last = self._last_by_host.get(host, 0.0)
        delta = now - last
        if delta < self._min_interval:
            time.sleep(self._min_interval - delta)
        self._last_by_host[host] = time.monotonic()

    def _throttle(self, host: str) -> None:
        now = time.monotonic()
        last = self._last_by_host.get(host, 0.0)
        delta = now - last
        if delta < self._min_interval:
            time.sleep(self._min_interval - delta)
        self._last_by_host[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        """RFC 9309-ish: 404 → allow; 5xx → block; other 4xx → allow; 2xx → parse.
        The robots fetch itself is throttled like any host traffic."""
        host = urlparse(url).netloc
        self._throttle(host)
        resp = self._client.get(f"https://{host}/robots.txt", follow_redirects=True)
        if resp.status_code == 404:
            return True
        if resp.status_code >= 500:
            return False
        if resp.status_code >= 400:
            return True
        rp = robotparser.RobotFileParser()
        rp.parse(resp.text.splitlines())
        return rp.can_fetch("*", url)
