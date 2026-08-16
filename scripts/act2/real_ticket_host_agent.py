#!/usr/bin/env python3
"""Démo 15.5+ (ticket réel #8331) — phase HOST-AGENT : génère K candidats sur
le vrai ticket (état buggy = parent du fix commit, tests = suites du fix
commit) puis les mesure réellement (node --test sur worktree dédié).
DIVULGATION : le prompt étend la classe gelée au multi-fichiers (exigé par un
ticket réel) — forme conservée : symptôme seul, T=0.7, max_tokens 16000,
mêmes auteurs. Le texte du commit-solution n'est JAMAIS dans le prompt.
Run: uv run python scripts/act2/real_ticket_host_agent.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "data" / "landing" / "act2-pilot" / "real-ticket-8331"
SESSION = DEMO / "session"
HOST = "Kimsufi-standard"
WORKTREE = "~/OmniRoute-demo8331"
F2P = [
    "#8331 non-streaming: client-facing usage.prompt_tokens equals raw upstream value, not +2000",
    "#8331 streaming: SSE usage frame (addBufferToUsage + filterUsageForFormat chain) is not inflated",
    "#8331 Claude-format streaming frame: input_tokens stays real, not buffered",
    "#8331 addBufferToUsage still computes the safety margin internally (buffer not deleted)",
    "addBufferToUsage — #8331: keeps DEFAULT 2000 out of client-visible prompt_tokens, exposes it via context_budget_prompt_tokens",
    "addBufferToUsage — respects USAGE_TOKEN_BUFFER=500 env override via context_budget_* fields",
    "addBufferToUsage — also computes context_budget_input_tokens for Claude-format input_tokens",
    "setBufferTokensCache(500) — immediately sets custom buffer value in context_budget_* fields",
    "invalidateBufferTokensCache — still resets to null (returns DEFAULT on next sync call)",
]
MODELS = [("DeepSeek-V4-Flash", 4), ("GLM-5.2-NVFP4", 4)]

spec = importlib.util.spec_from_file_location("gg", ROOT / "scripts" / "act2" / "genfam_gen.py")
gg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gg)
_specx = importlib.util.spec_from_file_location("prx", ROOT / "scripts" / "act2" / "pilot_run.py")
PRX = importlib.util.module_from_spec(_specx)
sys.modules["pilot_run"] = PRX
_specx.loader.exec_module(PRX)
MODEL_OVERRIDE = {"m": ""}


def call_t07(prompt: str) -> dict:
    key = os.environ.get("LI_GALERE_KEY") or os.environ.get("OPENCODE_GALERE_KEY")
    body = json.dumps({"model": MODEL_OVERRIDE["m"],
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.7, "max_tokens": 16000})
    cmd = ["curl", "-sS", "--max-time", "580", "-X", "POST", gg.pr.GALERE,
           "-H", "Content-Type: application/json", "-H", "User-Agent: opencode/1.0",
           "--data-binary", "@-"]
    if key:
        cmd += ["-H", f"Authorization: Bearer {key}"]
    p = subprocess.run(cmd, input=body.encode(), capture_output=True, check=False)
    j = json.loads(p.stdout.decode())
    mm = j["choices"][0]["message"]
    return {"text": (mm.get("content") or "") + "\n" +
            (mm.get("reasoning") or mm.get("reasoning_content") or ""),
            "usage": j.get("usage", {}),
            "sha": sha256(p.stdout).hexdigest()}


def build_prompt() -> str:
    ticket = ("The 2000-token context-window safety buffer is being folded into the "
              "client-visible usage fields. Real API request of 69 upstream prompt tokens "
              "comes back to the client as ~2069 prompt_tokens (and input_tokens/total_tokens "
              "likewise inflated). The safety margin must still be computed internally "
              "(context_budget_* fields), but the client-facing metering fields must stay real.\n")
    ut = (DEMO / "buggy" / "usageTracking.ts").read_text()
    cub = (DEMO / "buggy" / "clientUsageBuffer.ts").read_text()
    cc = (DEMO / "buggy" / "chatCore.ts").read_text().splitlines()
    excerpt = "\n".join(f"{i+4151}: {l}" for i, l in enumerate(cc[4150:4310]))
    tests = "\n".join(f"- {t}" for t in F2P)
    return (ticket +
            "\nFAILING TESTS (all must pass after your fix, names exact):\n" + tests +
            "\n\nFILE open-sse/utils/usageTracking.ts (full):\n```\n" + ut +
            "\n```\n\nFILE open-sse/handlers/chatCore/clientUsageBuffer.ts (full):\n```\n" + cub +
            "\n```\n\nFILE open-sse/handlers/chatCore.ts (excerpt, lines 4151-4310, call site at 4241):\n```\n" + excerpt +
            "\n```\n\nReturn ONLY a unified diff inside ```diff fences with real a/ b/ paths "
            "(git apply compatible). Minimal change, no comments in the diff.")


def sh(cmd: str, t: int = 600) -> str:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                          capture_output=True, text=True, check=False, timeout=t).stdout


def measure_candidate(cid: str, diff: str) -> dict:
    out = {"id": cid}
    sh(f"cd {WORKTREE} && git status --porcelain open-sse | wc -l")
    dirty = sh(f"cd {WORKTREE} && git status --porcelain open-sse | head -1").strip()
    if dirty:
        out["error"] = f"worktree dirty: {dirty}"
        return out
    Path("/tmp/tsv6/cand.diff").write_text(diff if diff.endswith("\n") else diff + "\n")
    subprocess.run(["scp", "-q", "/tmp/tsv6/cand.diff", f"{HOST}:/tmp/cand-8331.diff"],
                   capture_output=True, check=False, timeout=60)
    sha_pre = {f: sh(f"sha256sum {WORKTREE}/{f} | cut -c1-16").strip()
               for f in ("open-sse/utils/usageTracking.ts",
                         "open-sse/handlers/chatCore/clientUsageBuffer.ts",
                         "open-sse/handlers/chatCore.ts")}
    ap = sh(f"cd {WORKTREE} && git apply --recount /tmp/cand-8331.diff 2>&1")
    applied = any(sha_pre[f] != sh(f"sha256sum {WORKTREE}/{f} | cut -c1-16").strip() for f in sha_pre)
    if not applied:
        sh(f"cd {WORKTREE} && patch -p1 -l --fuzz=3 -s < /tmp/cand-8331.diff 2>&1")
        applied = any(sha_pre[f] != sh(f"sha256sum {WORKTREE}/{f} | cut -c1-16").strip() for f in sha_pre)
        out["apply_mode"] = "fuzz" if applied else None
    else:
        out["apply_mode"] = "strict-git"
    out["applied"] = applied
    if not applied:
        out["apply_out"] = ap[-200:]
        return out
    tests = ("tests/unit/8331-usage-buffer-inflation.test.ts "
             "tests/unit/usage-token-buffer.test.ts")
    raw = sh(f"cd {WORKTREE} && node --import tsx/esm --test --test-reporter=tap {tests} 2>&1", t=400)
    failed, passed = [], 0
    for line in raw.splitlines():
        l = line.strip()
        if l.startswith("not ok "):
            failed.append(l[7:].split(" # ")[0].strip())
        elif l.startswith("ok "):
            passed += 1
    f2p_set = set(F2P)
    f2p_red = sorted(f2p_set & set(failed))
    p2p_failed = [t for t in failed if t not in f2p_set]
    out.update({"f2p_red": f2p_red, "p2p_failed": p2p_failed, "n_passed": passed,
                "y": 1 if (not f2p_red and not p2p_failed) else 0})
    sh(f"cd {WORKTREE} && git checkout -- open-sse && rm -f /tmp/cand-8331.diff")
    return out


def main() -> int:
    SESSION.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt()
    print(f"prompt: {len(prompt)} chars (~{len(prompt)//4} tokens), F2P={len(F2P)}")
    (SESSION / "prompt.txt").write_text(prompt)
    log = SESSION / "call-log.jsonl"
    n = 0
    for model, k in MODELS:
        MODEL_OVERRIDE["m"] = model
        for d in range(1, k + 1):
            n += 1
            cid = f"r{n:02d}-{model.split('-')[0].lower()}-d{d}"
            g = call_t07(prompt)
            row = {"ts": datetime.now(UTC).isoformat(), "id": cid, "model": model,
                   "prompt_sha256": sha256(prompt.encode()).hexdigest()[:16],
                   "reply_sha256": g["sha"][:16], "usage": g["usage"]}
            san = PRX.extract_diff_sanitized(g["text"])
            if san:
                (SESSION / f"{cid}.diff").write_text(san + "\n")
                m = measure_candidate(cid, san + "\n")
            else:
                m = {"id": cid, "applied": False, "error": "pas de fence diff exploitable"}
            row.update(m)
            with log.open("a") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{cid}: applied={m.get('applied')} y={m.get('y')} "
                  f"f2p_red={len(m.get('f2p_red', []))} p2p_broken={len(m.get('p2p_failed', []))}"
                  + (f" ERR={m.get('error', '')[:40]}" if m.get("error") else ""), flush=True)
    print("HOST-AGENT DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
