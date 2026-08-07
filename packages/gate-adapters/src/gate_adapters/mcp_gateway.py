"""MCP gateway adapter (story 8.4, FR-25's second setup): the Model Context
Protocol's documented message path — `tools/call` JSON-RPC — intercepted
BEFORE the tool executes, advisory back into the response.

Same seam as the Claude Code hook (gate.intercept/serve). Advisory only: the
response enriches `result` with an advisory annotation block; blocking verbs
don't exist here either. Offline-deterministic; exits by returning, never by
raising into a client.
"""

from __future__ import annotations

import json

from core_schema.errors import SchemaError
from gate.intercept import CandidateCtx
from gate.serve import GateServer

_PATCH_METHOD_PREFIXES = ("tools/call",)


def parse_mcp_call(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise SchemaError("LI-GADPT-001", "MCP message not valid JSON", {}) from exc
    if not isinstance(payload, dict):
        raise SchemaError("LI-GADPT-001", "MCP message not a mapping", {})
    if payload.get("jsonrpc") != "2.0":
        raise SchemaError("LI-GADPT-001", "not a JSON-RPC 2.0 message", {})
    return payload


def candidate_from_mcp(payload: dict, *, wire_hash: str) -> CandidateCtx | None:
    if payload.get("method") != "tools/call":
        return None
    params = payload.get("params")
    if not isinstance(params, dict):
        raise SchemaError("LI-GADPT-001", "tools/call without params mapping", {})
    name = params.get("name", "")
    if not isinstance(name, str):
        raise SchemaError("LI-GADPT-001", "tool name not text", {})
    if not any(k in name.lower() for k in ("edit", "write", "patch", "apply")):
        return None  # non-mutating tool — no annotation
    args = params.get("arguments")
    if not isinstance(args, dict):
        raise SchemaError("LI-GADPT-001", "tools/call arguments not a mapping", {})
    content = args.get("content") or args.get("new_string") or args.get("patch")
    if not isinstance(content, str) or not content.strip():
        raise SchemaError("LI-GADPT-001", "patch tool call without text content", {})
    path = args.get("path") or args.get("file_path") or "unknown/path.py"
    if "\n" in str(path) or not str(path).strip():
        raise SchemaError("LI-GADPT-001", "path malformed", {})
    diff = (f"--- a/{path}\n+++ b/{path}\n@@ mcp-captured @@\n"
            + "\n".join(f"+{line}" for line in content.splitlines()) + "\n")
    return CandidateCtx(repo=str(args.get("repo", "local/working-copy")),
                        patch_diff=diff,
                        rationale_ptr="governance/probe-design/model-strategy-v1.md",
                        wire_payload_sha256=wire_hash)


def run_mcp_message(raw: str, server: GateServer) -> dict:
    """The interception: annotate, and answer with an ADVISORY-enriched result.
    Abstention = the plain result (refusal recorded in the log)."""
    from hashlib import sha256

    wire_hash = sha256(raw.encode("utf-8", errors="replace")).hexdigest()
    try:
        payload = parse_mcp_call(raw)
        ctx = candidate_from_mcp(payload, wire_hash=wire_hash)
        if ctx is None:
            return {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"status": "pass-through"}}

        from gate_adapters.claude_code_hooks import (
            AdapterSettings,
            target_tier_of,
        )

        tier = target_tier_of(ctx, AdapterSettings(server.snapshot.root, server.snapshot.predictor_hash,
                                                   server.log_path, server.user_test_selection))
        ev = server.handle(ctx, prediction_target_tier=tier, model_family="baseline")
        if ev.kind == "prediction_refused":
            return {"jsonrpc": "2.0", "id": payload.get("id"),
                    "result": {"status": "pass-through"}}
        p = ev.payload
        anno = (f"[latent-imagination] advisory — flip probability {p['flip_probability']:.2f} "
                f"(mesuré {p['predictor_disclosure']['measured_precision']}, sub-barre, "
                f"{p['corpus_version']}) — méthodologie: {ctx.rationale_ptr}")
        return {"jsonrpc": "2.0", "id": payload.get("id"),
                "result": {"status": "annotated", "advisory": anno,
                           "flip_probability": p["flip_probability"],
                           "predictor_disclosure": p["predictor_disclosure"]}}
    except SchemaError as exc:
        # coded refusal rides the wire as data, never a protocol exception
        return {"jsonrpc": "2.0", "id": None,
                "result": {"status": "adapter-abstained", "reason": str(exc)[:200]}}
