"""Harvest policy loader (Task 0). The policy is a committed, pre-registered TOML
(PR R10); loading a missing/invalid one fails loud with a stable code — never a
silent default, since the caps are the governance."""

from __future__ import annotations

import tomllib
from pathlib import Path

from core_schema.errors import SchemaError
from pydantic import BaseModel, ConfigDict


class _Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rest_requests_per_day: int
    harvest_window_days: int
    max_diff_fetches_per_repo_day: int


class _Politeness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    per_host_min_interval_s: float
    on_403_429: str
    secondary_backoff: str


class _Rights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    license_allowlist: list[str]
    unknown_license: str


class _NoiseHandling(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dedup: str
    flaky: str
    sanitization: str


class _DriftWatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_atif_version: str


class HarvestPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    registered_at: str
    budget: _Budget
    politeness: _Politeness
    rights: _Rights
    noise_handling: _NoiseHandling
    drift_watch: _DriftWatch


def load_policy(path: Path) -> HarvestPolicy:
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError as exc:
        raise SchemaError("LI-CORPUS-001", "harvest policy not found", {"path": str(path)}) from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise SchemaError("LI-CORPUS-002", "harvest policy not parseable TOML/UTF-8", {"err": str(exc)}) from exc
    if not isinstance(data.get("policy"), dict):
        raise SchemaError("LI-CORPUS-001", "harvest policy missing [policy] table", {})
    # [policy] carries the identity fields; the other top-level tables carry the sections.
    payload = {k: v for k, v in data.items() if k != "policy"} | data["policy"]
    try:
        return HarvestPolicy.model_validate(payload)
    except ValueError as exc:
        raise SchemaError("LI-CORPUS-002", "harvest policy invalid", {"err": str(exc)}) from exc
