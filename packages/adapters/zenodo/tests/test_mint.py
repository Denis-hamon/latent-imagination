"""Zenodo minter (story 2.6 task 4 close) — fully offline (MockTransport)."""

from __future__ import annotations

import httpx
import pytest
from core_schema.errors import SchemaError
from zenodo_push.mint import mint_doi


def _server():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/deposit/depositions" and request.method == "POST":
            return httpx.Response(201, json={
                "id": 42,
                "links": {"bucket": "https://files.example/bkt-1"},
            })
        if request.url.path == "/bkt-1/release.tar.gz" and request.method == "PUT":
            return httpx.Response(201, json={"key": "release.tar.gz"})
        if request.url.path.endswith("/actions/publish") and request.method == "POST":
            return httpx.Response(202, json={
                "metadata": {"doi": "10.5281/zenodo.42"},
                "links": {"record_html": "https://zenodo.org/records/42"},
            })
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_full_mint_flow(tmp_path):
    client, calls = _server()
    tarball = tmp_path / "release.tar.gz"
    tarball.write_bytes(b"PAR1 fake-tar")
    res = mint_doi(client, tarball, {"title": "t"}, api_base="https://api.example/api",
                   token="tok")
    assert res.doi == "10.5281/zenodo.42"
    assert res.deposition_id == 42
    methods = [m for m, _ in calls]
    assert methods == ["POST", "PUT", "POST"]  # create → upload → publish, in order


def test_create_refusal_is_coded(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(SchemaError) as ei:
        mint_doi(client, tmp_path / "x.tgz", {}, api_base="https://api.example/api", token=None)
    # tarball doesn't exist either, but creation refused FIRST
    assert ei.value.code == "LI-ZEN-001"


def test_missing_upload_source_coded(tmp_path):
    client, _ = _server()
    with pytest.raises(SchemaError) as ei:
        mint_doi(client, tmp_path / "absent.tar.gz", {}, api_base="https://api.example/api", token=None)
    assert ei.value.code == "LI-ZEN-002"


def test_upload_or_publish_refusal_coded(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "actions" not in request.url.path:
            return httpx.Response(201, json={"id": 1, "links": {"bucket": "https://f/b"}})
        if request.method == "PUT":
            return httpx.Response(500)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    f = tmp_path / "a.tgz"
    f.write_bytes(b"x")
    with pytest.raises(SchemaError) as ei:
        mint_doi(client, f, {}, api_base="https://api.example/api", token=None)
    assert ei.value.code == "LI-ZEN-002"
