"""Claude Code PreToolUse adapter (story 5.3 + CR, FR-18/FR-19, NFR-V1).

Reads the documented PreToolUse hook event on stdin, annotates through the
5.1 seam, prints an advisory JSON to stdout, exits 0 on EVERY path — including
misconfiguration (the deployer sees ONE systemMessage, never a traceback loop).

Wire shape: `systemMessage` (shown to the USER) + `hookSpecificOutput.
additionalContext` (reaches the AGENT — Claude Code's documented advisory
channel). Blocking keys (`permissionDecision`, `decision`, `continue`) are
NEVER emitted — not hidden: absent, and a test proves it.

v1 scope: file patch tools (Edit/Write/MultiEdit). Bash and NotebookEdit are
recorded abstentions, not silent holes. Stdin is capped. No network.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from core_schema.errors import SchemaError
from gate.intercept import CandidateCtx
from gate.serve import GateServer

_PATCH_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})
_NOTEBOOK = "NotebookEdit"
_TESTISH_PATH = re.compile(r"(^|/)(tests?|spec|test_[^/]*|conftest)(\.|/|$)", re.IGNORECASE)
_STDIN_CAP = 8 * 1024 * 1024


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


def read_stdin(stdin_buffer=None) -> str:
    """Bounded, decode-tolerant stdin (a hook never dies on input bytes)."""
    buf = stdin_buffer or sys.stdin.buffer
    raw = buf.read(_STDIN_CAP + 1)
    if len(raw) > _STDIN_CAP:
        raise SchemaError("LI-GADPT-003", "hook stdin over the 8 MiB cap", {})
    return raw.decode("utf-8", errors="replace")


def parse_hook_event(raw: str) -> tuple[str, dict]:
    """(tool_name, tool_input). Coded errors; never a bare exception in a hook."""
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise SchemaError("LI-GADPT-001", "hook stdin not valid JSON", {}) from exc
    if not isinstance(payload, dict):
        raise SchemaError("LI-GADPT-001", "hook payload not a mapping", {})
    if payload.get("hook_event_name", "PreToolUse") != "PreToolUse":
        # Not ours to annotate (e.g. PostToolUse misregistration) — silent pass.
        return "__not_pre__", {}
    name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(name, str) or not isinstance(tool_input, dict):
        raise SchemaError("LI-GADPT-001", "hook payload lacks tool_name/tool_input", {})
    return name, tool_input


def _require_str(d: dict, key: str, tool: str) -> str:
    v = d.get(key)
    if not isinstance(v, str):
        raise SchemaError("LI-GADPT-001", f"{tool}.{key} missing or not text", {"got": type(v).__name__})
    return v


def _check_path(p: str) -> str:
    if not p or "\n" in p or "\r" in p or "\x00" in p:
        raise SchemaError("LI-GADPT-001", "file_path malformed", {})
    return p


def candidate_from(tool_name: str, tool_input: dict,
                   wire_payload_sha256: str | None = None) -> CandidateCtx | None:
    """Reconstruct a minimal unified-diff approximation from the file tools.
    None for non-patch tools; malformed payloads RAISE (coded) — a partial
    fabricated annotation is worse than none (CR 5.3)."""
    if tool_name == _NOTEBOOK:
        raise SchemaError("LI-GADPT-001", "NotebookEdit unsupported in v1 (recorded abstention)", {})
    if tool_name not in _PATCH_TOOLS:
        return None
    path = _check_path(_require_str(tool_input, "file_path", tool_name))
    if tool_name == "Write":
        old, new = "", _require_str(tool_input, "content", tool_name)
    elif tool_name == "Edit":
        old = _require_str(tool_input, "old_string", tool_name)
        new = _require_str(tool_input, "new_string", tool_name)
    else:  # MultiEdit
        edits = tool_input.get("edits")
        if not isinstance(edits, list) or not edits or not all(isinstance(e, dict) for e in edits):
            raise SchemaError("LI-GADPT-001", "MultiEdit.edits missing/not a list of objects", {})
        old = "\n".join(_require_str(e, "old_string", tool_name) for e in edits)
        new = "\n".join(_require_str(e, "new_string", tool_name) for e in edits)
    diff = (f"--- a/{path}\n+++ b/{path}\n@@ hook-captured @@\n"
            + "\n".join(f"-{line}" for line in old.splitlines())
            + "\n"
            + "\n".join(f"+{line}" for line in new.splitlines())
            + "\n")
    return CandidateCtx(
        repo=tool_input.get("repo", "local/working-copy"),
        patch_diff=diff,
        rationale_ptr="governance/probe-design/model-strategy-v1.md",
        wire_payload_sha256=wire_payload_sha256,
    )


def target_tier_of(ctx: CandidateCtx, settings: AdapterSettings) -> str | None:
    """Tier by the PATCH'S FILE PATHS only — content words never trigger (CR 5.3)."""
    paths = re.findall(r"^\+\+\+ b/(.+)$", ctx.patch_diff, re.MULTILINE)
    if any(_TESTISH_PATH.search(p) for p in paths):
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
    """Advisory wire: systemMessage (user) + additionalContext (agent).
    The blocking channels (`permissionDecision`, `decision`, `continue`) are
    never present — advisory by construction."""
    if event_kind != "gate_annotated":
        return {}  # abstention: empty wire; the log records the refusal
    msg = advisory_message(payload["corpus_version"], payload["flip_probability"],
                           payload["predictor_disclosure"])
    return {
        "systemMessage": msg,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": msg,
        },
    }


def run_hook(stdin_text: str, server: GateServer) -> int:
    """The hook body. Exits 0 whatever happens — a hook crash must not break
    the user's loop."""
    from hashlib import sha256 as _sha

    wire_hash = _sha(stdin_text.encode("utf-8", errors="replace")).hexdigest()
    try:
        tool_name, tool_input = parse_hook_event(stdin_text)
        if tool_name == "__not_pre__":
            return 0
        ctx = candidate_from(tool_name, tool_input, wire_payload_sha256=wire_hash)
        if ctx is None:
            return 0
        settings = AdapterSettings(
            snapshot_root=server.snapshot.root, predictor_hash=server.snapshot.predictor_hash,
            log_path=server.log_path, user_test_selection=server.user_test_selection,
        )
        ev = server.handle(ctx, prediction_target_tier=target_tier_of(ctx, settings),
                           model_family="baseline")
        sys.stdout.write(json.dumps(_output_json(ev.kind, ev.payload)) + "\n")
    except SchemaError as exc:
        print(f"[latent-imagination] adapter error (non-blocking): {exc}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — hook law: exit 0 no matter what
        print(f"[latent-imagination] adapter fault (non-blocking): {type(exc).__name__}", file=sys.stderr)
    return 0


def main() -> int:
    """Even MISCONFIGURED, the hook exits 0 after one visible, honest message —
    a traceback loop on every edit is the failure mode this guards (CR 5.3)."""
    try:
        from gate_adapters.settings import load_settings

        s = load_settings()
        server = GateServer.load(s.snapshot_root, expected_predictor_hash=s.predictor_hash,
                                 log_path=s.log_path, user_test_selection=s.user_test_selection)
        return run_hook(read_stdin(), server)
    except Exception as exc:  # noqa: BLE001 — deliberate: hook law outranks coding pride
        sys.stdout.write(json.dumps({
            "systemMessage": f"[latent-imagination] advisory inactif: {exc} — "
                             "voir ~/.latent-imagination ou LI_GATE_* (setup requis)"
        }) + "\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
