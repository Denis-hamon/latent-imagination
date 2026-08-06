"""Runs enumeration / cursor / pair deposits (story 4.1 + review fixes).
Fully offline. NOTE: the fixture lists runs NEWEST-FIRST ([102, 101]) — the
real GitHub order; the pre-review suite listed them ascending and masked P1."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from ci_logs.fetcher import Fetcher
from ci_logs.runs import Cursor, harvest_repo, load_cursor, repo_dirname, save_cursor
from corpus.policy import load_policy

POLICY = Path(__file__).resolve().parents[4] / "governance" / "corpus" / "harvest-policy-v1.toml"


def _policy():
    return load_policy(POLICY)


class FakeSleeper:
    def __init__(self) -> None:
        self.slept: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


def _api_client(now: int = 1_000_000_000):
    """NEWEST-FIRST runs; .diff web endpoints; license; one PR base lookup."""
    diff_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /")
        if path == "/api/repos/o/r/actions/runs":
            return httpx.Response(200, json={
                "workflow_runs": [
                    {"id": 102, "head_sha": "def456", "head_branch": "main", "event": "push",
                     "conclusion": "success", "created_at": "2026-08-01T01:00:00Z",
                     "run_attempt": 1, "pull_requests": []},
                    {"id": 101, "head_sha": "abc123", "head_branch": "feat", "event": "pull_request",
                     "conclusion": "failure", "created_at": "2026-08-01T00:00:00Z",
                     "run_attempt": 1, "pull_requests": [{"number": 7}]},
                ]
            })
        if path == "/api/repos/o/r/license":
            return httpx.Response(200, json={"license": {"spdx_id": "MIT"}})
        if path == "/api/repos/o/r/pulls/7":
            return httpx.Response(200, json={"base": {"sha": "ba5e17"}, "number": 7})
        if path == "/o/r/commit/def456.diff":
            diff_calls.append("def456")
            return httpx.Response(200, content=b"diff --git a/y.py b/y.py\n+ok\n")
        if path == "/o/r/commit/abc123.diff":
            diff_calls.append("abc123")
            return httpx.Response(200, content=b"diff --git a/x.py b/x.py\n+fix\n")
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler)), diff_calls


def _harvest(tmp_path, client=None):
    client = client or _api_client()[0]
    fx = Fetcher(client, min_interval_s=0, sleeper=lambda s: None)
    return harvest_repo(fx, "o/r", tmp_path, _policy(), api_base="http://x/api", web_base="http://x")


def test_cursor_roundtrip_atomic_and_cases(tmp_path):
    c = Cursor(repo="o/r", page=2, last_run_id=101)
    save_cursor(tmp_path / ".cursor.json", c)
    assert load_cursor(tmp_path / ".cursor.json", "o/r") == c
    (tmp_path / ".cursor.json.tmp").write_text('{"partial"')
    assert load_cursor(tmp_path / ".cursor.json", "o/r") == c
    assert load_cursor(tmp_path / "absent.json", "o/r") is None


def test_cursor_corrupt_or_foreign_repo_fails_loud(tmp_path):
    from core_schema.errors import SchemaError

    p = tmp_path / ".cursor.json"
    p.write_text("{nope")
    with pytest.raises(SchemaError):
        load_cursor(p, "o/r")
    save_cursor(tmp_path / "c2.json", Cursor(repo="other/repo", page=1, last_run_id=5))
    with pytest.raises(SchemaError) as ei:  # P8: cross-repo cursor must never interleave
        load_cursor(tmp_path / "c2.json", "o/r")
    assert ei.value.code == "LI-CILOG-002"


def test_dirname_encoding_is_injective():
    assert repo_dirname("a_per_b/c") != repo_dirname("a/b_per_c")
    assert repo_dirname("o/r") == "o-r"


def test_harvest_deposits_pairs_provenance_v2(tmp_path):
    res = _harvest(tmp_path)
    assert res.new_pairs == 2
    d = tmp_path / "ci-logs" / "o-r" / "101"
    prov = json.loads((d / "provenance.json").read_text())
    assert prov["registry_source_id"] == "github-actions-public-ci"
    assert prov["repo"] == "o/r" and prov["head_sha"] == "abc123"
    assert prov["base_sha"] == "ba5e17"  # PR base captured (P4)
    assert prov["run_conclusion"] == "failure" and prov["license"] == "MIT"


def test_rerun_newest_first_is_zero_write_zero_fetch(tmp_path):
    """P1 regression: with the REAL descending order, a rerun lands nothing
    and — decisive — issues NO diff fetch at all."""
    client, diff_calls = _api_client()
    assert _harvest(tmp_path, client).new_pairs == 2
    assert len(diff_calls) == 2
    second = _harvest(tmp_path, client)
    assert second.new_pairs == 0
    assert len(diff_calls) == 2  # unchanged — membership by directory
    # manifest lineage intact (P12): merged, not overwritten
    m = json.loads((tmp_path / "ci-logs" / "o-r" / ".harvest-manifest.json").read_text())
    assert len(m["deposited"]) == 2


def test_max_pairs_stops_and_resume_picks_up_the_remainder(tmp_path):
    client, diff_calls = _api_client()
    fx = Fetcher(client, min_interval_s=0, sleeper=lambda s: None)
    first = harvest_repo(fx, "o/r", tmp_path, _policy(), max_pairs=1,
                         api_base="http://x/api", web_base="http://x")
    assert first.new_pairs == 1
    second = harvest_repo(fx, "o/r", tmp_path, _policy(), max_pairs=1,
                          api_base="http://x/api", web_base="http://x")
    assert second.new_pairs == 1  # the page remainder is NOT lost (P1)
    assert len(diff_calls) == 2  # exactly the two distinct diffs, once each


def test_empty_repo_first_harvest_no_crash(tmp_path):
    """P3 regression: zero runs + no cursor must still write cursor+manifest."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/repos/e/r/actions/runs":
            return httpx.Response(200, json={"workflow_runs": []})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fx = Fetcher(client, min_interval_s=0, sleeper=lambda s: None)
    res = harvest_repo(fx, "e/r", tmp_path, _policy(), api_base="http://x/api", web_base="http://x")
    assert res.new_pairs == 0
    assert (tmp_path / "ci-logs" / "e-r" / ".cursor.json").exists()
    assert (tmp_path / "ci-logs" / "e-r" / ".harvest-manifest.json").exists()


def test_budget_cap_stops_and_discloses(tmp_path, monkeypatch):
    """P5: the diff cap is mechanical; stopping is disclosed, never silent."""
    policy = _policy()
    monkeypatch.setattr(policy.budget, "max_diff_fetches_per_repo_day", 1)
    client, _ = _api_client()
    fx = Fetcher(client, min_interval_s=0, sleeper=lambda s: None)
    first = harvest_repo(fx, "o/r", tmp_path, policy, api_base="http://x/api", web_base="http://x")
    assert first.new_pairs == 1  # cap spent after exactly one diff
    second = harvest_repo(fx, "o/r", tmp_path, policy, api_base="http://x/api", web_base="http://x")
    assert second.new_pairs == 0  # budget file says spent → stops before fetching
    assert second.manifest["budget"]["stopped"] is not None


def test_unconcluded_runs_are_not_landed(tmp_path):
    """P9: a running CI job must not mint a 'conclusion=None' item."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /")
        if request.url.path == "/api/repos/o/r/actions/runs":
            return httpx.Response(200, json={"workflow_runs": [
                {"id": 105, "head_sha": "zzz999", "conclusion": None, "event": "push",
                 "created_at": "2026-08-02T00:00:00Z", "run_attempt": 1, "pull_requests": []},
            ]})
        if request.url.path == "/api/repos/o/r/license":
            return httpx.Response(200, json={"license": {"spdx_id": "MIT"}})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fx = Fetcher(client, min_interval_s=0, sleeper=lambda s: None)
    res = harvest_repo(fx, "o/r", tmp_path, _policy(), api_base="http://x/api", web_base="http://x")
    assert res.new_pairs == 0
    assert not (tmp_path / "ci-logs" / "o-r" / "105").exists()


def test_license_transient_failure_aborts_not_unknowns(tmp_path):
    """P10: 403 on the license endpoint after the backoff chain = LI-CILOG-005 path gone —
    api_get's hard failure (LI-CILOG-001) is what aborts; the audit-queue flood is impossible
    because harvesting never starts (license lookup precedes any diff fetch)."""
    now = 1_000_000_000

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /")
        if request.url.path.endswith("/actions/runs"):
            return httpx.Response(200, json={"workflow_runs": [
                {"id": 7, "head_sha": "aaaaaaa", "conclusion": "failure", "event": "push",
                 "created_at": "2026-08-02T00:00:00Z", "run_attempt": 1, "pull_requests": []},
            ]})
        if request.url.path.endswith("/license"):
            return httpx.Response(403, headers={
                "x-ratelimit-remaining": "0", "x-ratelimit-reset": str(now)})
        return httpx.Response(404)

    sleeper = FakeSleeper()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    fx = Fetcher(client, min_interval_s=0, sleeper=sleeper, time_fn=lambda: now - 10)
    from core_schema.errors import SchemaError

    with pytest.raises(SchemaError) as ei:
        harvest_repo(fx, "o/r", tmp_path, _policy(), api_base="http://x/api", web_base="http://x")
    assert ei.value.code == "LI-CILOG-001"
    assert not list(tmp_path.rglob("patch.diff"))  # zero spend on diffs


def test_diff_url_with_query_string_stays_a_patch(tmp_path):
    """P16: '…/commit/<sha>.diff?plain=1' must deposit patch.diff, not log.txt."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /")
        return httpx.Response(200, content=b"diff --git a/x b/x\n+1\n")

    fx = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), min_interval_s=0)
    r = fx.fetch("https://ci.example/o/r/commit/abc.diff?plain=1", tmp_path, "s", "9")
    assert r.path.name == "patch.diff"
    assert "sha256_patch" in r.provenance


def test_malformed_rate_headers_are_tolerated(tmp_path):
    """P15: garbage x-ratelimit-* must not crash the retry path."""
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /")
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"x-ratelimit-remaining": "abc", "retry-after": "banana"})
        return httpx.Response(200, content=b"ok")

    sleeper = FakeSleeper()
    fx = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)),
                 min_interval_s=0, sleeper=sleeper)
    r = fx.fetch("https://ci.example/x", tmp_path, "s", "r")
    assert r.path.read_bytes() == b"ok"
    assert sleeper.slept[0] == 60.0  # registered secondary backoff step 1


def test_settings_build_client_authorization(tmp_path, monkeypatch):
    from ci_logs.settings import CiLogsSettings, build_client

    monkeypatch.setenv("LI_GITHUB_TOKEN", "ghp_example")
    c = build_client(CiLogsSettings())
    assert c.headers["authorization"] == "Bearer ghp_example"
    monkeypatch.delenv("LI_GITHUB_TOKEN")
    assert "authorization" not in build_client(CiLogsSettings()).headers
