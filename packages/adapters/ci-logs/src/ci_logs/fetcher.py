"""CI-logs spike adapter: fetch public CI logs with robots/rate-limit care.

httpx (adapter-only network dep per AD-6 exemption). Tests use httpx.MockTransport —
no network in tests, ever.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
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
        self._last = 0.0

    def fetch(self, url: str, dest_dir: Path, source_id: str, run_id: str) -> FetchResult:
        self._respect_robots(url)
        self._throttle()
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

    def _throttle(self) -> None:
        now = time.monotonic()
        delta = now - self._last
        if delta < self._min_interval:
            time.sleep(self._min_interval - delta)
        self._last = time.monotonic()

    def _respect_robots(self, url: str) -> None:
        host = urlparse(url).netloc
        resp = self._client.get(f"https://{host}/robots.txt")
        if resp.status_code == 200 and "Disallow: /" == resp.text.strip():
            raise PermissionError(f"robots.txt disallows {host}")
