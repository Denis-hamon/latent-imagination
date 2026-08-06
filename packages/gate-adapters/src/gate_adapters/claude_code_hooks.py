"""Claude Code PreToolUse adapter (story 5.3, FR-18/FR-19, NFR-V1).

Reads the documented PreToolUse hook event on stdin, annotates through the
5.1 seam, prints ONE advisory `systemMessage` JSON to stdout, exits 0 on every
path. Blocking channels (`permissionDecision`, `decision: "block"`) are NEVER
emitted — not hidden: absent (a test proves it).

v1 scope: patch-bearing file tools (Edit/Write/MultiEdit). Bash tool calls are
out of scope (documented). Offline-deterministic: no network.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from core_schema.errors import SchemaError
from gate.intercept import CandidateCtx
from gate.serve import GateServer

_PATCH_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})
_TESTISH = ("test", "spec", "conftest")


@dataclass(frozen=True)
class AdapterSettings:
    snapshot_root: Path
    predictor_hash: str
    log_path: Path
    user_test_selection: str | None = None

    @classmethod
    def from_env(cls) -> AdapterSettings:
        from gate_adapters.settings import load_settings

        return load_settings()


def parse_hook_event(raw: str) -> tuple[str, dict]:
    """(tool_name, tool_input). Coded errors; never a bare exception in a hook."""
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise SchemaError("LI-GADPT-001", "hook stdin not valid JSON", {}) from exc
    if not isinstance(payload, dict):
        raise SchemaError("LI-GADPT-001", "hook payload not a mapping", {})
    name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(name, str) or not isinstance(tool_input, dict):
        raise SchemaError("LI-GADPT-001", "hook payload lacks tool_name/tool_input", {})
    return name, tool_input


def candidate_from(tool_name: str, tool_input: dict) -> CandidateCtx | None:
    """Reconstruct a minimal unified-diff approximation from the file tools.
    None for non-patch tools (no annotation is the honest output there)."""
    if tool_name not in _PATCH_TOOLS:
        return None
    path = tool_input.get("file_path")
    if not isinstance(path, str) or not path:
        raise SchemaError("LI-GADPT-001", "patch tool without file_path", {"tool": tool_name})
    if tool_name == "Write":
        old, new = "", tool_input.get("content", "")
    elif tool_name == "Edit":
        old, new = tool_input.get("old_string", ""), tool_input.get("new_string", "")
    else:  # MultiEdit
        edits = tool_input.get("edits") or []
        old = "\n".join(e.get("old_string", "") for e in edits if isinstance(e, dict))
        new = "\n".join(e.get("new_string", "") for e in edits if isinstance(e, dict))
    diff = (f"--- a/{path}\n+++ b/{path}\n@@ hook-captured @@\n"
            + "\n".join(f"-{line}" for line in old.splitlines())
            + "\n"
            + "\n".join(f"+{line}" for line in new.splitlines())
            + "\n")
    return CandidateCtx(
        repo=tool_input.get("repo", "local/working-copy"),
        patch_diff=diff,
        rationale_ptr="governance/probe-design/model-strategy-v1.md",
    )


def target_tier_of(ctx: CandidateCtx, settings: AdapterSettings) -> str | None:
    low = ctx.patch_diff.lower()
    if any(t in low for t in _TESTISH):
        return "diff_touched"
    if settings.user_test_selection:
        return "user_designated"
    return None  # abstain (OQ-10)


def advisory_message(corpus_version: str, p: float, disclosure: dict) -> str:
    return (f"[latent-imagination] advisory — flip probability {p:.2f} "
            f"(precision mesurée {disclosure.get('measured_precision')}, posture sub-barre, "
            f"corpus {corpus_version}) — méthodologie: "
            "governance/probe-design/model-strategy-v1.md")


def _output_json(event_kind: str, payload: dict) -> dict:
    """Advisory wire shape: systemMessage only. Never the blocking channels."""
    if event_kind == "gate_annotated":
        return {"systemMessage": advisory_message(
            payload["corpus_version"], payload["flip_probability"], payload["predictor_disclosure"])}
    return {}  # abstention stays silent on the wire (the log records it)


def run_hook(stdin_text: str, server: GateServer) -> int:
    """The hook body. ALWAYS exits 0 — a hook crash must never break the loop."""
    try:
        tool_name, tool_input = parse_hook_event(stdin_text)
        ctx = candidate_from(tool_name, tool_input)
        if ctx is None:
            return 0
        settings = server_settings(server)
        ev = server.handle(ctx, prediction_target_tier=target_tier_of(ctx, settings),
                           model_family="baseline")
        sys.stdout.write(json.dumps(_output_json(ev.kind, ev.payload)) + "\n")
    except SchemaError as exc:
        print(f"[latent-imagination] adapter error (non-blocking): {exc}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — hook law: exit 0 no matter what
        print(f"[latent-imagination] adapter fault (non-blocking): {type(exc).__name__}", file=sys.stderr)
    return 0


def server_settings(server: GateServer) -> AdapterSettings:
    return AdapterSettings(
        snapshot_root=server.snapshot.root, predictor_hash=server.snapshot.predictor_hash,
        log_path=server.log_path, user_test_selection=None,
    )


def main() -> int:
    from gate_adapters.settings import load_settings

    s = load_settings()
    server = GateServer.load(s.snapshot_root, expected_predictor_hash=s.predictor_hash,
                             log_path=s.log_path)
    return run_hook(sys.stdin.read(), server)


if __name__ == "__main__":
    raise SystemExit(main())
