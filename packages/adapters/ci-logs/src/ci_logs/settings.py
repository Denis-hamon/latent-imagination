"""ci-logs settings (AR-7: token via env only, never committed).

`LI_GITHUB_TOKEN` feeds the optional Authorization header. Unauthenticated
fallback is documented: 60 req/h REST instead of 5,000/h — fine for a fixture
run, hopeless for a window. The policy caps count requests either way.
"""

from __future__ import annotations

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict


class CiLogsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LI_")

    github_token: str | None = None


def build_client(settings: CiLogsSettings | None = None) -> httpx.Client:
    s = settings or CiLogsSettings()
    headers = {"Accept": "application/vnd.github+json"}
    if s.github_token:
        headers["Authorization"] = f"Bearer {s.github_token}"
    return httpx.Client(headers=headers, timeout=60.0)
