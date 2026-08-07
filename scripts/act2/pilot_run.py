#!/usr/bin/env python3
"""Act II pilot executor — split-site honest: Mac calls galere, node runs docker.

Real discipline: each task → OFF-arm (direct patch) + ON-arm (advisory-regen if
pinned predictor flip-prob ≥ 0.5). ALL calls recorded. Reports land in
data/landing/act2-pilot results/ with the budget usage.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

GALERE = "https://ai.galere.org/v1/chat/completions"
MODEL = "DeepSeek-V4-Flash"  # 2026-08-07: L4 sleeves switch — Kimi rambles (UA callback timeout); Flash is the fastest family at galere and syntaxes true diffs
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
        "temperature": 0.2, "max_tokens": 16000,
    })
    cmd = ["curl", "-sS", "--max-time", "580", "-X", "POST", GALERE,
           "-H", "Content-Type: application/json", "-H", "User-Agent: opencode/1.0",
           "--data-binary", "@-", ]
    if key:
        cmd += ["-H", f"Authorization: Bearer {key}"]
    p = subprocess.run(cmd, input=body.encode(), capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"curl galere failed rc={p.returncode}: {p.stderr[-300:].decode()}")
    j = json.loads(p.stdout.decode())
    m = j["choices"][0]["message"]
    return {"text": (m.get("content") or "") + "\n" + (m.get("reasoning") or m.get("reasoning_content") or ""),
            "usage": j.get("usage", {})}


def extract_diff(text: str) -> str | None:
    import re

    m = re.search(r"```(?:diff|patch)\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"(?ms)^diff --git .+", text)
    return m.group(0) if m else None


def _predictor():
    from gate.ports import load_pinned_snapshot
    from gate.predict import PinnedPredictor

    snap = ROOT / "governance" / "act2" / "arm-artifacts"
    return PinnedPredictor.from_snapshot(
        load_pinned_snapshot(snap, expected_predictor_hash=sha256(
            (snap / "predictor.json").read_bytes()).hexdigest()))


def gen_patch(task: dict) -> dict:
    prompt = (
        "Fix the failing tests. Output ONLY a unified diff inside ```diff fences.\n\n"
        f"TASK: {task['problem'][:2500]}\n\nFAILING TESTS: {'; '.join(task['f2p'][:6])}"
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
            diff = extract_diff(g["raw_reply"])
            rec["patch_sha256"] = sha256((diff or "").encode()).hexdigest() if diff else None
            rec["prompt_sha256"] = g["prompt_sha256"]
            rec["reply_sha256"] = g["reply_sha256"]
            if arm == "on" and diff:
                p = pred.score(diff)
                rec["flip_probability"] = p
                if p >= THRESH:
                    regen_prompt = (
                        f"TASK: {task['problem'][:2500]}\n\nYour previous patch probaly fails "
                        f"(our instrument predicts flip probability {p:.2f}). Rework with care, "
                        "output only the ```diff block."
                    )
                    g2 = call_model(regen_prompt)
                    calls += 1
                    rec["regen_reply_sha256"] = sha256(g2["text"].encode()).hexdigest()
                    diff2 = extract_diff(g2["text"])
                    rec["patch_sha256"] = sha256((diff2 or diff or "").encode()).hexdigest() if (diff2 or diff) else None
                    rec["advisory_regen"] = True
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
