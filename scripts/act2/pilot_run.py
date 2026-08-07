#!/usr/bin/env python3
"""Act II pilot executor — split-site honest: Mac calls galere, node runs docker.

Real discipline: each task → OFF-arm (direct patch) + ON-arm (advisory-regen if
pinned predictor flip-prob ≥ 0.5). ALL calls recorded. Reports land in
data/landing/act2-pilot results/ with the budget usage.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

GALERE = "https://ai.galere.org/v1/chat/completions"
MODEL = os.environ.get("PILOT_MODEL", "DeepSeek-V4-Flash")  # 2026-08-07: L4 sleeves switch — Kimi rambles (UA callback timeout); Flash is the fastest family at galere and syntaxes true diffs
THRESH = 0.5
ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
TASKS = PILOT / "pilot-tasks.json"
RESULTS = PILOT / "results"
LOG = PILOT / "call-log.jsonl"


def call_model(prompt: str) -> dict:
    """NdD galere answers httpx with 502 on this UA path but accepts curl.

    Same endpoint, same headers — so we shell out to the tool that works.
    """
    import os

    key = os.environ.get("LI_GALERE_KEY") or os.environ.get("OPENCODE_GALERE_KEY")
    body = json.dumps({
        "model": MODEL, "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2, "max_tokens": 6000,
    })
    cmd = ["curl", "-sS", "--max-time", "580", "-X", "POST", GALERE,
           "-H", "Content-Type: application/json", "-H", "User-Agent: opencode/1.0",
           "--data-binary", "@-", ]
    if key:
        cmd += ["-H", f"Authorization: Bearer {key}"]
    p = subprocess.run(cmd, input=body.encode(), capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"curl galere failed rc={p.returncode}: {p.stderr[-300:].decode()}")
    for attempt in (1, 2):
        try:
            j = json.loads(p.stdout.decode())
            break
        except json.JSONDecodeError:
            if attempt == 1 and b"timeout" in p.stdout.lower():
                print(f"  retry galere (timeout) attempt 2 — {len(prompt)} chars", flush=True)
                p = subprocess.run(cmd, input=body.encode(), capture_output=True, check=False)
                continue
            raise RuntimeError(f"galere non-JSON rc={p.returncode} head={p.stdout[:300]!r}") from None
    m = j["choices"][0]["message"]
    return {"text": (m.get("content") or "") + "\n" + (m.get("reasoning") or m.get("reasoning_content") or ""),
            "usage": j.get("usage", {})}


def sanitize_diff(diff: str) -> str:
    """Strip chatty tags (`</diff>`…) and trailing non-diff tail; keep only
    diff-syntax lines (hunk operators, context, headers)."""
    keep = []
    prefixes = ("--- ", "+++ ", "@@ ", "index ", "diff --git ", "new file", "old mode", "new mode")
    for ln in diff.splitlines():
        s = ln.rstrip()
        if s.startswith(("+diff>", "</diff>", "</patch>", "</change>")):
            continue
        if s.startswith(prefixes) or s.startswith(("-", "+", " ", "\\ ")):
            keep.append(s)
        elif not keep:  # pre-diff chatter
            continue
        else:
            break  # first non-diff line ends the diff
    out = "\n".join(keep)
    return out + "\n" if out else ""


def extract_diff(text: str) -> str | None:
    import re

    m = re.search(r"```(?:diff|patch)\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"(?ms)^diff --git .+", text)
    if m:
        return m.group(0)
    # dernier seuil : une cloture classique ---/+++ seule (certains modèles
    # omettent 'diff --git'); on exige ---/+++ + @@ d'un même hunk
    m = re.search(r"(?ms)^--- [ab]/.+\n\+\+\+ [ab]/.+\n@@ .+", text)
    if m and "@@ " in m.group(0):
        return m.group(0)
    return None


def extract_diff_sanitized(text: str) -> str | None:
    raw = extract_diff(text)
    if raw is None:
        return None
    clean = sanitize_diff(raw)
    return clean or None


def extract_full_file(text: str) -> str | None:
    import re

    m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"```\n(.*?)```", text, re.DOTALL)
    if m and "def " in m.group(1):
        return m.group(1)
    return None


def make_diff(original: str, modified: str, rel: str) -> str:
    """Deterministic unified diff — the model never hallucinates hunks again."""
    import difflib

    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
        n=3,
    )
    return "".join(diff)


def _predictor():
    from gate.ports import load_pinned_snapshot
    from gate.predict import PinnedPredictor

    snap = ROOT / "governance" / "act2" / "arm-artifacts"
    return PinnedPredictor.from_snapshot(
        load_pinned_snapshot(snap, expected_predictor_hash=sha256(
            (snap / "predictor.json").read_bytes()).hexdigest()))


def apply_diff(loc_old: str, patch: str, rel: str) -> bool:
    """True iff the diff applies cleanly to loc_old using git apply --check
    (p1-style paths)."""
    import subprocess, tempfile

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(loc_old)
        subprocess.run(["git", "-C", td, "init", "-q"], capture_output=True)
        # retry 1: strict. retry 2: --recount tolerates LLM's hallucinated @@ counts
        for args in (["apply", "--recount", "-"], ["apply", "-"]):
            r = subprocess.run(["git", "-C", td, *args], input=patch, capture_output=True, text=True)
            if r.returncode == 0:
                d = subprocess.run(["git", "-C", td, "diff", "--stat"], capture_output=True, text=True)
                return True
        return False


def apply_and_export_debug(loc_old: str, patch: str, rel: str) -> tuple[str | None, str]:
    """Like apply_and_export but returns (clean_diff, stderr_or_empty)."""
    import subprocess, tempfile

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(loc_old)
        subprocess.run(["git", "-C", td, "init", "-q"], capture_output=True)
        subprocess.run(["git", "-C", td, "add", "-f", rel], capture_output=True)
        r = subprocess.run(
            ["git", "-C", td, "apply", "--recount", "-"],
            input=patch, capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None, r.stderr
        out = subprocess.run(
            ["git", "-C", td, "diff", "--no-color", "--no-ext-diff", "--", rel],
            capture_output=True, text=True,
        )
        if not out.stdout.strip():
            return None, "diff empty after apply (no net change)"
        return out.stdout, ""


def apply_and_export(loc_old: str, patch: str, rel: str) -> str | None:
    """Apply model diff locally, re-emit as clean `git diff` (correct hunks).
    None if patch fails even with --recount."""
    import subprocess, tempfile

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(loc_old)
        subprocess.run(["git", "-C", td, "init", "-q"], capture_output=True)
        r = subprocess.run(
            ["git", "-C", td, "apply", "--recount", "-"],
            input=patch, capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None
        # produce a clean diff relative to the baseline content
        out = subprocess.run(
            ["git", "-C", td, "diff", "--no-color", "--no-ext-diff", "--", rel],
            capture_output=True, text=True,
        )
        if not out.stdout.strip():
            return None
        # git diff prefixes paths with a/ b/ natively
        return out.stdout


def buggy_src_path(task: dict) -> Path:
    """The post-bug-state file the agent actually sees inside the image."""
    key = task["instance_id"].replace("/", "_")
    return ROOT / "data" / "landing" / "act2-pilot" / f"{key}.buggy.py"


def gen_patch(task: dict) -> dict:
    p = buggy_src_path(task)
    src = p.read_text() if p.is_file() else ""
    target = task.get("target", "the affected file")
    prompt = (
        "Fix failing tests. Think briefly, then output EXACTLY ONE block: a unified "
        "diff inside ```diff fences (paths a/<file> b/<file>). No reasoning text "
        "outside the fences.\n"
        f"File to patch: {target}\n\n"
        f"TASK: {task['problem'][:1200]}\n\nFAILING TESTS: {'; '.join(task['f2p'][:6])}\n\n"
        f"CURRENT CONTENT (verbatim):\n```python\n{src}\n```"
    )
    out = call_model(prompt)
    return {"prompt_sha256": sha256(prompt.encode()).hexdigest(),
            "reply_sha256": sha256(out["text"].encode()).hexdigest(),
            "raw_reply": out["text"], "usage": out["usage"], "api_calls": 1}


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    tasks = json.loads(TASKS.read_text())
    pred = _predictor()
    calls = 0
    for task in tasks:
        iid = task["instance_id"]
        for arm in ("off", "on"):
            rec: dict = {"task": iid, "arm": arm, "run_at": datetime.now(UTC).isoformat()}
            g = gen_patch(task)
            calls += 1
            _p = buggy_src_path(task)
            original = _p.read_text() if _p.is_file() else ""
            edited = extract_full_file(g["raw_reply"])
            if edited and original:
                orig_lines = len(original.splitlines())
                edit_lines = len(edited.splitlines())
                # flag rewrites that destroy >50% of the file — the model lied about "whole file"
                if edit_lines < orig_lines * 0.5:
                    rec["rewrite_suspect"] = f"orig={orig_lines} edited={edit_lines}"
                    edited = None  # fall through to raw extraction
                rec["edited_lines"] = edit_lines
            if edited and original and edited.strip() != original.strip():
                diff = make_diff(original, edited, task["target"])
                rec["diff_mode"] = "regenerated"
            else:
                raw = extract_diff_sanitized(g["raw_reply"])
                if raw and original:
                    diff, err = apply_and_export_debug(original, raw + "\n", task["target"])
                    if diff is None:
                        rec["apply_stderr"] = err[-400:]
                else:
                    diff = None
                rec["diff_mode"] = (
                    "model-applied-reexport" if diff is not None
                    else ("unappliable" if raw else "no-diff")
                )
            rec["patch_sha256"] = sha256((diff or "").encode()).hexdigest() if diff else None
            rec["prompt_sha256"] = g["prompt_sha256"]
            rec["reply_sha256"] = g["reply_sha256"]
            if not diff:  # the extract-miss keeps the raw reply for the audit trail
                rec["reply_preview"] = g["raw_reply"][:600]
            if arm == "on" and diff:
                p = pred.score(diff)
                rec["flip_probability"] = p
                if p >= THRESH:
                    regen_prompt = (
                        "Regenerate. Your previous attempt is predicted to fail F2P "
                        "(our instrument predicts failure). Output ONLY a unified "
                        "diff inside ```diff fences — no prose. Minimal, targeted, "
                        "mechanical fix."
                    )
                    g2 = call_model(regen_prompt)
                    calls += 1
                    rec["regen_reply_sha256"] = sha256(g2["text"].encode()).hexdigest()
                    edited2 = extract_full_file(g2["text"])
                    diff2 = make_diff(original, edited2, task["target"]) if (edited2 and original) else None
                    rec["patch_sha256"] = sha256((diff2 or diff or "").encode()).hexdigest() if (diff2 or diff) else None
                    rec["advisory_regen"] = diff2 is not None
            # write patch + task meta to be executed on the node
            work = RESULTS / f"{iid.replace('/', '_')}-{arm}"
            work.mkdir(exist_ok=True)
            (work / "patch.diff").write_text(diff or "")
            (work / "meta.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
            (work / "task.json").write_text(json.dumps(task, indent=1))
            print(f"{iid[:40]:40} arm={arm} patch={'yes' if diff else 'no'} calls={calls}")
    with LOG.open("a") as fh:
        fh.write(json.dumps({"ts": datetime.now(UTC).isoformat(), "pilot_calls": calls}) + "\n")
    print(f"calls used this pilot: {calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
