"""MCP gateway adapter (story 8.4 + CR, FR-25 second setup): interception on the
documented JSON-RPC 2.0 `tools/call` path.

Protocol law (2.0 §4.1/§5): notifications (no `id`) get NO reply; replies echo
the request id — INCLUDING soft-refusals issued after a successful parse.
Advisory only; the mutating-tool surface is an EXPLICIT allowlist (CR 8.4:
substring grep was unsound in both directions).
"""

from __future__ import annotations

import json
import re
from hashlib import sha256

from core_schema.errors import SchemaError
from gate.intercept import CandidateCtx
from gate.serve import GateServer

MCP_SPEC_PIN = "Model Context Protocol, schema revision 2025-06-18"
_MAX_MESSAGE = 8 * 1024 * 1024
_MAX_CONTENT = 2 * 1024 * 1024

# explicit allowlist — unlisted tools pass through observed-but-unannotated
_MUTATING_TOOLS = frozenset({
    "edit_file", "write_file", "apply_patch", "multi_edit", "create_file",
    "delete_file", "move_file", "replace_lines", "insert_at", "update_file",
    "replace_text",
})
_BAD_PATH = re.compile(r"(\.\.)|(^\s)|(\s$)|[\t\x00]")


def parse_mcp_call(raw: str) -> dict:
    if not isinstance(raw, str):
        raise SchemaError("LI-GADPT-001", "MCP message not text", {"got": type(raw).__name__})
    if len(raw) > _MAX_MESSAGE:
        raise SchemaError("LI-GADPT-001", "MCP message over the 8 MiB cap", {})
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise SchemaError("LI-GADPT-001", "MCP message not valid JSON", {}) from exc
    if not isinstance(payload, dict):
        raise SchemaError("LI-GADPT-001", "MCP message not a mapping (batch arrays unsupported)", {})
    if payload.get("jsonrpc") != "2.0":
        raise SchemaError("LI-GADPT-001", "not a JSON-RPC 2.0 message", {})
    return payload


def candidate_from_mcp(payload: dict) -> CandidateCtx | None:
    """tools/call on an allowlisted mutating tool → candidate. Notifications and
    non-mutating tools → None (caller handles the reply rules)."""
    if payload.get("method") != "tools/call":
        return None
    params = payload.get("params")
    if not isinstance(params, dict):
        raise SchemaError("LI-GADPT-001", "tools/call without params mapping", {})
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise SchemaError("LI-GADPT-001", "tools/call name missing/not text", {})
    if name not in _MUTATING_TOOLS:
        return None
    args = params.get("arguments")
    if not isinstance(args, dict):
        raise SchemaError("LI-GADPT-001", "tools/call arguments not a mapping", {})
    content = args.get("content", args.get("new_string", args.get("patch")))
    if not isinstance(content, str) or not content.strip():
        raise SchemaError("LI-GADPT-001", "patch tool call without text content", {})
    if len(content) > _MAX_CONTENT:
        raise SchemaError("LI-GADPT-001", "patch content over the 2 MiB cap", {})
    old = args.get("old_string")
    old_text = old if isinstance(old, str) else ""
    path = args.get("path", args.get("file_path", "unknown/path.py"))
    if not isinstance(path, str) or not path or _BAD_PATH.search(path):
        raise SchemaError("LI-GADPT-001", "path malformed (traversal/blank/control)", {})
    diff = (f"--- a/{path}\n+++ b/{path}\n@@ mcp-captured @@\n"
            + "\n".join(f"-{line}" for line in old_text.splitlines())
            + ("\n" if old_text else "")
            + "\n".join(f"+{line}" for line in content.splitlines()) + "\n")
    return CandidateCtx(repo=str(args.get("repo", "local/working-copy")),
                        patch_diff=diff,
                        rationale_ptr="governance/probe-design/model-strategy-v1.md",
                        wire_payload_sha256=sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())


def run_mcp_message(raw: str, server: GateServer) -> dict | None:
    """Notification → None (never reply). calls → annotated/pass-through/soft-coded."""
    request_id = None
    try:
        payload = parse_mcp_call(raw)
        request_id = payload.get("id")  # carried into EVERY response path
        if "id" not in payload:
            m = payload.get("method")
            if candidate_from_mcp(payload) is not None and m == "tools/call":
                # a mutating notification still annotates+log but gets no reply
                _annotate(payload, server)
            return None
        if payload.get("method") != "tools/call":
            return None
        ctx = candidate_from_mcp(payload)
        if ctx is None:
            return {"jsonrpc": "2.0", "id": request_id, "result": {"status": "pass-through"}}
        return _annotate(payload, server)
    except SchemaError as exc:
        if request_id is None:
            return None  # unparseable notification: say nothing
        return {"jsonrpc": "2.0", "id": request_id,
                "result": {"status": "adapter-abstained", "reason": str(exc)[:200]}}


def _annotate(payload: dict, server: GateServer) -> dict:
    from gate_adapters.claude_code_hooks import AdapterSettings, target_tier_of

    ctx = candidate_from_mcp(payload)
    tier = target_tier_of(ctx, AdapterSettings(server.snapshot.root, server.snapshot.predictor_hash,
                                               server.log_path, server.user_test_selection))
    ev = server.handle(ctx, prediction_target_tier=tier, model_family="baseline")
    request_id = payload.get("id")
    if ev.kind == "prediction_refused":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"status": "pass-through"}}
    p = ev.payload
    anno = (f"[latent-imagination] advisory — flip probability {p['flip_probability']:.2f} "
            f"(mesuré {p['predictor_disclosure']['measured_precision']}, sub-barre, "
            f"{p['corpus_version']}) — méthodologie: {ctx.rationale_ptr} — "
            f"wire: {MCP_SPEC_PIN}")
    return {"jsonrpc": "2.0", "id": request_id,
            "result": {"status": "annotated", "advisory": anno,
                       "flip_probability": p["flip_probability"],
                       "predictor_disclosure": p["predictor_disclosure"]}}
