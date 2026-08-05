"""Proof tests for the AD-14 gate LLM-client scan."""

from __future__ import annotations

from pathlib import Path

from tests.guards.dependency_scan_gate import find_gate_llm_violations


def test_gate_has_no_llm_clients_on_real_tree():
    assert find_gate_llm_violations() == []


def test_guard_flags_llm_client_in_gate(tmp_path):
    fake = tmp_path / "packages"
    gate = fake / "gate"
    gate.mkdir(parents=True)
    (gate / "pyproject.toml").write_text(
        '[project]\nname = "li-gate"\nversion = "0.1.0"\nrequires-python = ">=3.14"\n'
        'dependencies = ["openai==1.99.0"]\n'
    )
    harness = fake / "harness"
    harness.mkdir()
    (harness / "pyproject.toml").write_text(
        '[project]\nname = "li-harness"\nversion = "0.1.0"\nrequires-python = ">=3.14"\n'
        'dependencies = ["openai"]\n'
    )
    violations = find_gate_llm_violations(Path(fake))
    assert violations == ["gate: declares LLM client 'openai'"]
