"""Zenodo adapter — the DOI minter (edge; the ONLY place Zenodo network lives).

Flow per the published REST contract (developers.zenodo.org):
  1. POST {api}/deposit/depositions            → deposition id + files bucket URL
  2. PUT  {bucket}/{filename}                  → file uploaded (streamed bytes)
  3. POST {api}/deposit/depositions/{id}/actions/publish → 202, DOI minted

The sandbox vs prod base is a constructor argument — never hard-code prod in
tests. Tokens come from the environment ONLY (AR-7): never logged, never in
the repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
from core_schema.errors import SchemaError

SANDBOX_API = "https://sandbox.zenodo.org/api"
PROD_API = "https://zenodo.org/api"


@dataclass(frozen=True)
class MintResult:
    deposition_id: int
    doi: str
    record_url: str


class ZenodoMinter:
    def __init__(self, client: httpx.Client, *, api_base: str = PROD_API, token: str | None):
        self._client = client
        self._api = api_base.rstrip("/")
        self._token = token

    def _headers(self, json_ct: bool = True) -> dict:
        h = {}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        if json_ct:
            h["Content-Type"] = "application/json"
        return h

    def create_deposition(self, metadata: dict) -> tuple[int, str]:
        r = self._client.post(f"{self._api}/deposit/depositions",
                              json={"metadata": metadata}, headers=self._headers())
        if r.status_code != 201:
            raise SchemaError("LI-ZEN-001", "deposition creation refused",
                              {"status": r.status_code, "body": r.text[:300]})
        body = r.json()
        try:
            dep_id = int(body["id"])
            bucket = str(body["links"]["bucket"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SchemaError("LI-ZEN-001", "deposition response malformed", {}) from exc
        return dep_id, bucket

    def upload_file(self, bucket_url: str, path: Path, *, remote_name: str | None = None) -> None:
        path = Path(path)
        if not path.is_file():
            raise SchemaError("LI-ZEN-002", "upload source missing", {"path": str(path)})
        name = remote_name or path.name
        with path.open("rb") as fh:
            data = fh.read()
        r = self._client.put(f"{bucket_url.rstrip('/')}/{name}", content=data,
                             headers=self._headers(json_ct=False))
        if r.status_code not in (200, 201):
            raise SchemaError("LI-ZEN-002", "file upload refused",
                              {"status": r.status_code, "name": name})

    def publish(self, deposition_id: int) -> MintResult:
        r = self._client.post(f"{self._api}/deposit/depositions/{deposition_id}/actions/publish",
                              headers=self._headers())
        if r.status_code != 202:
            raise SchemaError("LI-ZEN-003", "publish refused",
                              {"status": r.status_code, "id": deposition_id})
        body = r.json()
        doi = str((body.get("metadata") or {}).get("doi") or "")
        if not doi:
            doi = str(((body.get("metadata") or {}).get("prereserve_doi") or {}).get("doi") or "")
        url = str((body.get("links") or {}).get("record_html")
                  or (body.get("links") or {}).get("html") or "")
        return MintResult(deposition_id=deposition_id, doi=doi, record_url=url)


def mint_doi(client: httpx.Client, tarball: Path, metadata: dict, *,
             api_base: str, token: str | None) -> MintResult:
    """create → upload → publish, or raise a coded error. Never catches silently."""
    z = ZenodoMinter(client, api_base=api_base, token=token)
    dep_id, bucket = z.create_deposition(metadata)
    z.upload_file(bucket, tarball)
    return z.publish(dep_id)
