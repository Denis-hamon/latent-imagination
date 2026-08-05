"""ATIF v1.7 trace models: golden fixture + business rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core_schema.errors import SchemaError
from core_schema.trace import ExecutionTrace

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class TestGoldenFixture:
    def test_valid_trace_validates(self):
        trace = ExecutionTrace.model_validate(load("valid_trace_v1.json"))
        trace.validate_business_rules()
        assert trace.schema_version == "ATIF-v1.7"
        assert trace.agent.tool_definitions is not None
        assert trace.steps[1].llm_call_count == 1
        assert trace.steps[1].metrics.cost_usd > 0
        assert trace.extra["attempt"]["task_id"]  # our payload rides extra.*

    def test_naive_timestamp_variant(self):
        with pytest.raises(SchemaError) as exc:
            ExecutionTrace.model_validate(load("invalid_naive_timestamp.json"))
        assert exc.value.code == "LI-SCHEMA-002"

    def test_step_id_sequence_variant(self):
        with pytest.raises(SchemaError) as exc:
            ExecutionTrace.model_validate(
                load("invalid_step_ids.json")
            ).validate_business_rules()
        assert exc.value.code == "LI-SCHEMA-005"

    def test_unknown_tool_call_ref_variant(self):
        with pytest.raises(SchemaError) as exc:
            ExecutionTrace.model_validate(
                load("invalid_observation_ref.json")
            ).validate_business_rules()
        assert exc.value.code == "LI-SCHEMA-004"


class TestAgentOnlyFields:
    def test_model_name_on_user_step_rejected(self):
        valid = load("valid_trace_v1.json")
        valid["steps"][0]["model_name"] = "claude"  # user step
        with pytest.raises(SchemaError) as exc:
            ExecutionTrace.model_validate(valid)
        assert exc.value.code == "LI-SCHEMA-003"

    def test_unknown_toplevel_field_rejected(self):
        valid = load("valid_trace_v1.json")
        valid["steps"][1]["surprise"] = True
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ExecutionTrace.model_validate(valid)
