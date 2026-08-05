"""ci-logs adapter tests — fully offline via httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest
from ci_logs.fetcher import Fetcher


def _client(payload: bytes = b"log body", robots: bytes = b"User-agent: *\nAllow: /", status=200, robots_status=200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(robots_status, content=robots)
        return httpx.Response(status, content=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_writes_log_and_provenance(tmp_path):
    fx = Fetcher(_client(), min_interval_s=0)
    r = fx.fetch("http://ci.example/run/42/log", tmp_path, "public-ci-seed", "run-42")
    assert r.path.read_bytes() == b"log body"
    assert r.provenance["status"] == 200
    assert len(r.sha256) == 64


def test_robots_disallow_blocks(tmp_path):
    fx = Fetcher(_client(robots=b"Disallow: /", robots_status=200), min_interval_s=0)
    with pytest.raises(PermissionError):
        fx.fetch("http://ci.example/x", tmp_path, "s", "r")


def test_throttle_spacing(tmp_path):
    fx = Fetcher(_client(), min_interval_s=0.05)
    import time

    t0 = time.monotonic()
    fx.fetch("http://ci.example/a", tmp_path, "s", "1")
    fx.fetch("http://ci.example/b", tmp_path, "s", "2")
    assert time.monotonic() - t0 >= 0.05
