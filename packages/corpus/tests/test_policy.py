"""Harvest policy v1 (Task 0): the pre-registered caps are real, loadable, and
strictly positive; the ATIF drift-watch expectation matches the schema pin."""

from pathlib import Path
from typing import get_args

import pytest

POLICY_PATH = Path(__file__).resolve().parents[3] / "governance" / "corpus" / "harvest-policy-v1.toml"


def test_policy_loads_with_required_fields():
    from corpus.policy import load_policy

    p = load_policy(POLICY_PATH)
    assert p.version == 1
    assert p.registered_at == "2026-08-06"
    assert p.budget.rest_requests_per_day > 0
    assert p.budget.harvest_window_days > 0
    assert p.budget.max_diff_fetches_per_repo_day > 0
    assert p.politeness.per_host_min_interval_s > 0
    assert "MIT" in p.rights.license_allowlist
    assert p.rights.unknown_license == "audit-queue-only"
    assert p.noise_handling.dedup
    assert p.drift_watch.expected_atif_version.startswith("ATIF-")


def test_drift_watch_matches_the_schema_pin():
    from core_schema.trace import ExecutionTrace
    from corpus.policy import load_policy

    p = load_policy(POLICY_PATH)
    pin = get_args(ExecutionTrace.model_fields["schema_version"].annotation)[0]
    assert p.drift_watch.expected_atif_version == pin


def test_missing_policy_fails_loud():
    from core_schema.errors import SchemaError
    from corpus.policy import load_policy

    with pytest.raises(SchemaError) as ei:
        load_policy(Path("/nonexistent/policy.toml"))
    assert ei.value.code == "LI-CORPUS-001"
