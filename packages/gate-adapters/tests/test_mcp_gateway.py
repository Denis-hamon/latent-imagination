"""MCP gateway adapter (story 8.4, FR-25 second setup): JSON-RPC in, advisory
back, pass-through when out of scope, coded soft-refusals."""

from __future__ import annotations

import json
from pathlib import Path

from gate.serve import GateServer
from gate.testing import make_pinned_snapshot
from gate_adapters.mcp_gateway import run_mcp_message


def _server(tmp_path):
    root, phash = make_pinned_snapshot(tmp_path / "snap")
    return root, phash, GateServer.load(root, expected_predictor_hash=phash,
                                        log_path=tmp_path / "dep" / "decisions.jsonl")


def _call(name="edit_file", args=None, msg_id=7):
    return json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
                       "params": {"name": name, "arguments": args or {}}})


def test_parse_and_advisory(tmp_path):
    _root, _pin, server = _server(tmp_path)
    out = run_mcp_message(_call(args={"path": "tests/test_x.py",
                                      "content": "def test_ok():\n    assert True\n"}),
                          server)
    assert out["result"]["status"] == "annotated"
    assert "flip probability" in out["result"]["advisory"]
    assert out["result"]["flip_probability"] <= 1.0
    assert out["id"] == 7
    log = (tmp_path / "dep" / "decisions.jsonl").read_text()
    assert "gate_annotated" in log


def test_pass_through_non_mutating(tmp_path):
    _root, _pin, server = _server(tmp_path)
    out = run_mcp_message(_call(name="read_file", args={"path": "x.py"}), server)
    assert out["result"]["status"] == "pass-through"
    assert not (tmp_path / "dep" / "decisions.jsonl").exists()


def test_passthrough_non_tool_call_and_garbage(tmp_path):
    _root, _pin, server = _server(tmp_path)
    out = run_mcp_message(json.dumps({"jsonrpc": "2.0", "method": "resources/list",
                                      "id": 1}), server)
    assert out["result"]["status"] == "pass-through"
    out2 = run_mcp_message("{not json", server)
    assert out2["result"]["status"] == "adapter-abstained"


def test_abstains_when_no_tier(tmp_path):
    _root, _pin, server = _server(tmp_path)
    out = run_mcp_message(_call(args={"path": "pkg/core.py", "content": "x = 1\n"}), server)
    assert out["result"]["status"] == "pass-through"
    log = json.loads((tmp_path / "dep" / "decisions.jsonl").read_text().strip())
    assert log["kind"] == "prediction_refused"


def test_no_blocking_verb_anywhere():
    src = Path(__import__("gate_adapters.mcp_gateway", fromlist=["x"]).__file__).read_text()
    for banned in ('"deny"', '"block"', "interrupt_requested"):
        assert banned not in src
