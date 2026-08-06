"""Adapter settings (story 5.3, AR-7 pattern): env-only, LI_ prefix."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from gate_adapters.claude_code_hooks import AdapterSettings


class _Env(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LI_")

    gate_snapshot: Path = Path.home() / ".latent-imagination" / "snapshot"
    gate_predictor_sha256: str = ""
    gate_log: Path = Path.home() / ".latent-imagination" / "decisions.jsonl"
    gate_test_selection: str | None = None


def load_settings() -> AdapterSettings:
    e = _Env()
    from core_schema.errors import SchemaError
    from gate.ports import _SHA_RE

    if not _SHA_RE.fullmatch(e.gate_predictor_sha256):
        raise SchemaError("LI-GADPT-002", "LI_GATE_PREDICTOR_SHA256 must be the 64-hex pin",
                          {"got_len": len(e.gate_predictor_sha256)})
    return AdapterSettings(
        snapshot_root=e.gate_snapshot,
        predictor_hash=e.gate_predictor_sha256,
        log_path=e.gate_log,
        user_test_selection=e.gate_test_selection,
    )
