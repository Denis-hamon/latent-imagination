"""Claude Code adapter (story 5.3) — advisory wire shape, exit-0 law, ordering."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from hashlib import sha256
from pathlib import Path

from gate.serve import GateServer
from gate_adapters.claude_code_hooks import (
    AdapterSettings,
    candidate_from,
    parse_hook_event,
    run_hook,
    target_tier_of,
)


def _artifact(tmp_path):
    art = {
        "predictor_version": "probe-predictor-v0", "corpus_version": "corpus-v0",
        "measured": {"precision": 0.6271},
        "vectorizer": {"kind": "sklearn.HashingVectorizer", "n_features": 2**12,
                       "alternate_sign": False, "norm": "l2", "lowercase": True,
                       "token_pattern": r"\b\w\w+\b"},
        "model": {"kind": "logreg-sigmoid", "intercept": 0.5, "coefficients": [0.0] * 2**12},
    }
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "META.json").write_text(json.dumps(
        {"layout_version": "store-layout-v1", "store_version": "a" * 64}))
    (snap / "predictor.json").write_text(json.dumps(art, allow_nan=False))
    phash = sha256(json.dumps(art, allow_nan=False).encode()).hexdigest()
    server = GateServer.load(snap, expected_predictor_hash=phash,
                             log_path=tmp_path / "deployer" / "decisions.jsonl")
    return server


def _hook_edit(path="pkg/core.py", old="return 0", new="return 1"):
    return json.dumps({
        "hook_event_name": "PreToolUse", "tool_name": "Edit",
        "tool_input": {"file_path": path, "old_string": old, "new_string": new},
    })


def test_parse_happy_and_garbage():
    name, ti = parse_hook_event(_hook_edit())
    assert name == "Edit" and ti["file_path"] == "pkg/core.py"
    import pytest
    from core_schema.errors import SchemaError

    with pytest.raises(SchemaError):
        parse_hook_event("{not json")
    with pytest.raises(SchemaError):
        parse_hook_event('{"x": 1}')


def test_candidate_and_tiers():
    ctx = candidate_from("Edit", {"file_path": "tests/test_x.py", "old_string": "a", "new_string": "b"})
    assert ctx is not None and "tests/test_x.py" in ctx.patch_diff
    s = AdapterSettings(Path("/x"), "0" * 64, Path("/y"), None)
    assert target_tier_of(ctx, s) == "diff_touched"
    plain = candidate_from("Edit", {"file_path": "pkg/core.py", "old_string": "a", "new_string": "b"})
    assert target_tier_of(plain, s) is None  # abstain without designated selection
    s2 = AdapterSettings(Path("/x"), "0" * 64, Path("/y"), "tests/integration")
    assert target_tier_of(plain, s2) == "user_designated"
    assert candidate_from("Read", {"file_path": "x"}) is None  # non-patch tool


def test_advisory_wire_shape_and_no_blocking_channels(tmp_path):
    server = _artifact(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_hook(_hook_edit(path="tests/test_any.py"), server)
    out = buf.getvalue().strip()
    assert rc == 0
    payload = json.loads(out)
    assert "systemMessage" in payload
    assert "flip probability" in payload["systemMessage"]
    # advisory channel reaching the AGENT (per vendor contract) is present…
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "additionalContext" in payload["hookSpecificOutput"]
    # …while the blocking channels stay provably absent (FR-19):
    assert "permissionDecision" not in payload["hookSpecificOutput"]
    assert "decision" not in payload
    assert "continue" not in payload
    # telemetry written BEFORE the tool runs, by PreToolUsen construction — the
    # log exists NOW (pre-execution is real)
    log = Path(server.log_path)
    rec = json.loads(log.read_text(encoding="utf-8").strip())
    assert rec["kind"] == "gate_annotated"


def test_abstain_writes_silence_on_wire_but_records(tmp_path):
    server = _artifact(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_hook(_hook_edit(path="pkg/core.py"), server)  # no test paths, no designation
    assert rc == 0
    wire = buf.getvalue().strip()
    assert wire == "{}"  # abstention: exactly the empty object — no advisory shown
    rec = json.loads(Path(server.log_path).read_text(encoding="utf-8").strip())
    assert rec["kind"] == "prediction_refused"


def test_exit_zero_on_total_garbage(tmp_path):
    server = _artifact(tmp_path)
    assert run_hook("garbage{{{", server) == 0
    assert run_hook("", server) == 0
