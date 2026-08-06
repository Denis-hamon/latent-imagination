"""Runs enumeration / cursor / pair deposits (story 4.1) — fully offline."""

from __future__ import annotations

import json

import httpx
import pytest
from ci_logs.fetcher import Fetcher
from ci_logs.runs import Cursor, harvest_repo, load_cursor, save_cursor


class FakeSleeper:
    def __init__(self) -> None:
        self.slept: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


def _api_client(now: int = 1_000_000_000):
    """Two runs for o/r; .diff web endpoint; license endpoint; robots allow."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(f"{request.method} {path}")
        if path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /")
        if path == "/api/repos/o/r/actions/runs":
            return httpx.Response(200, json={
                "workflow_runs": [
                    {
                        "id": 101,
                        "head_sha": "abc123",
                        "head_branch": "main",
                        "event": "pull_request",
                        "conclusion": "failure",
                        "created_at": "2026-08-01T00:00:00Z",
                        "run_attempt": 1,
                        "pull_requests": [{"number": 7}],
                    },
                    {
                        "id": 102,
                        "head_sha": "def456",
                        "head_branch": "main",
                        "event": "push",
                        "conclusion": "success",
                        "created_at": "2026-08-01T01:00:00Z",
                        "run_attempt": 1,
                        "pull_requests": [],
                    },
                ]
            }, headers={"x-ratelimit-remaining": "4990", "x-ratelimit-reset": str(now + 3600)})
        if path == "/api/repos/o/r/license":
            return httpx.Response(200, json={"license": {"spdx_id": "MIT"}})
        if path == "/o/r/commit/abc123.diff":
            return httpx.Response(200, content=b"diff --git a/x.py b/x.py\n+fix\n")
        if path == "/o/r/commit/def456.diff":
            return httpx.Response(200, content=b"diff --git a/y.py b/y.py\n+ok\n")
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler), base_url=""), calls


def test_cursor_roundtrip_and_atomic(tmp_path):
    c = Cursor(repo="o/r", page=2, last_run_id=101)
    save_cursor(tmp_path / ".cursor.json", c)
    assert load_cursor(tmp_path / ".cursor.json") == c
    # a torn tmp file must not corrupt the real cursor
    (tmp_path / ".cursor.json.tmp").write_text('{"partial"')
    assert load_cursor(tmp_path / ".cursor.json") == c
    assert load_cursor(tmp_path / "absent.json") is None


def test_cursor_corrupt_fails_loud(tmp_path):
    p = tmp_path / ".cursor.json"
    p.write_text("{nope")
    from core_schema.errors import SchemaError

    with pytest.raises(SchemaError) as ei:
        load_cursor(p)
    assert ei.value.code == "LI-CILOG-002"


def test_harvest_repo_deposits_pairs_with_provenance_v2(tmp_path):
    client, _calls = _api_client()
    fx = Fetcher(client, min_interval_s=0)
    res = harvest_repo(client, fx, "o/r", tmp_path, api_base="http://x/api", web_base="http://x")
    assert res.new_pairs == 2
    d1 = tmp_path / "ci-logs" / "o_per_r" / "101"
    patch = d1 / "patch.diff"
    assert patch.read_bytes().startswith(b"diff --git a/x.py")
    prov = json.loads((d1 / "provenance.json").read_text())
    assert prov["source"] == "github-actions"
    assert prov["repo"] == "o/r"
    assert prov["head_sha"] == "abc123"
    assert prov["workflow_run_id"] == 101
    assert prov["run_conclusion"] == "failure"
    assert prov["pr_number"] == 7
    assert prov["license"] == "MIT"
    assert prov["robots"] == "allow"
    assert prov["sha256_patch"] == res.manifest["deposited"][0]["sha256"] == \
        __import__("hashlib").sha256(patch.read_bytes()).hexdigest()
    # cursor advanced past run 102 (listing order)
    cur = load_cursor(tmp_path / "ci-logs" / "o_per_r" / ".cursor.json")
    assert cur is not None and cur.last_run_id == 102


def test_harvest_repo_is_idempotent_under_cursor(tmp_path):
    client, _ = _api_client()
    fx = Fetcher(client, min_interval_s=0)
    first = harvest_repo(client, fx, "o/r", tmp_path, api_base="http://x/api", web_base="http://x")
    assert first.new_pairs == 2
    second = harvest_repo(client, fx, "o/r", tmp_path, api_base="http://x/api", web_base="http://x")
    assert second.new_pairs == 0  # cursor says both runs already landed


def test_unauthenticated_server_error_waits_then_hard_fails(tmp_path):
    now = 1_000_000_000

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /")
        return httpx.Response(403, headers={
            "x-ratelimit-remaining": "0", "x-ratelimit-reset": str(now + 120)
        })

    sleeper = FakeSleeper()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    fx = Fetcher(client, min_interval_s=0, sleeper=sleeper, time_fn=lambda: now)
    from core_schema.errors import SchemaError

    with pytest.raises(SchemaError) as ei:
        fx.fetch("https://ci.example/x", tmp_path, "s", "r")
    assert ei.value.code == "LI-CILOG-001"
    assert sleeper.slept and sleeper.slept[0] >= 120  # waited for the reset window


def test_403_then_recovers_retries_once(tmp_path):
    state = {"n": 0}
    now = 1_000_000_000

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /")
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(403, headers={
                "x-ratelimit-remaining": "0", "x-ratelimit-reset": str(now + 60)
            })
        return httpx.Response(200, content=b"log!")

    sleeper = FakeSleeper()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    fx = Fetcher(client, min_interval_s=0, sleeper=sleeper, time_fn=lambda: now)
    r = fx.fetch("https://ci.example/x", tmp_path, "s", "r")
    assert r.path.read_bytes() == b"log!"
    assert state["n"] == 2
