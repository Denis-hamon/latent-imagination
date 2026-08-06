"""Live agent measurement, done right: real model via OpenAI-compatible endpoint.

Omits vendor lock-in (works against ANY /v1/chat/completions). The point: a
task = parent's sources + fix commit's tests; the model writes a patch; we run
the test. ERBVE counts the flip outcome. On the record, on the node.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from hashlib import sha256
from pathlib import Path

import httpx

ENDPOINT = "https://ai.galere.org/v1/chat/completions"
AUTH_ENV = "OPENCODE_GALERE_KEY"  # exported on the node


def sh(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stderr[-400:]}")
    return r


def pick_fix_tasks(repo: Path, n: int, max_patch_lines: int = 40) -> list[dict]:
    log = sh(["git", "log", "--pretty=format:%H%x09%s", "-n", "2000"], cwd=repo).stdout
    out = []
    for line in log.splitlines():
        if not line.strip():
            continue
        sha_, subject = line.split("\t", 1)
        if not subject.lower().startswith(("fix", "bug", "corr")):
            continue
        files = sh(["git", "show", "--name-only", "--pretty=", sha_], cwd=repo).stdout.split()
        src = [f for f in files if f.endswith(".py") and "test" not in f]
        tests = [f for f in files if "test" in f and f.endswith(".py")]
        if len(src) != 1 or not tests:
            continue
        stat = sh(["git", "show", "--stat", "--pretty=", sha_, "--", src[0]], cwd=repo).stdout
        m = re.search(r"(\d+) insertion", stat)
        ins = int(m.group(1)) if m else 0
        if ins > max_patch_lines or ins == 0:
            continue
        parent = sh(["git", "rev-parse", f"{sha_}^"], cwd=repo).stdout.strip()
        out.append(
            {
                "fix_commit": sha_,
                "parent_commit": parent,
                "src_file": src[0],
                "test_files": tests[:1],
                "subject": subject,
            }
        )
        if len(out) >= n:
            break
    return out


def call_model(endpoint: str, model: str, prompt: str) -> dict:
    import os

    headers = {"Content-Type": "application/json", "User-Agent": "curl/8.18.0"}
    key = os.environ.get(AUTH_ENV)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    last_exc: Exception | None = None
    for attempt_i in range(4):
        try:
            r = httpx.post(
                endpoint,
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 32000},
                headers=headers,
                timeout=600.0,
            )
            r.raise_for_status()
            break
        except httpx.HTTPStatusError as e:
            last_exc = e
            # Endpoint catalogue moves mid-day; 404/502/503 = backoff & retry
            # (transient per Denis's config notes). Others (401/403) mean
            # something real — don't paper over them.
            if e.response.status_code in (404, 502, 503):
                time.sleep(10 * (attempt_i + 1))
                continue
            raise
    else:
        raise last_exc  # type: ignore[misc]
    j = r.json()
    choice = j["choices"][0]["message"]
    content = choice.get("content") or ""
    reasoning = choice.get("reasoning_content") or choice.get("reasoning") or ""
    combined = (content + "\n" + reasoning).strip()
    usage = j.get("usage") or {}
    return {"content": combined, "usage": usage, "model": j.get("model", model)}


def extract_diff(text: str) -> str | None:
    m = re.search(r"```(?:diff|patch)\n(.*?)```", text, re.DOTALL)
    if not m:
        m = re.search(r"(?ms)^diff --git .+", text)
        return m.group(0) if m else None
    return m.group(1)


PROMPT = (
    "OUTPUT RULES: no tool calls. No narration. No file inspection requests. "
    "Read the failing test output below and write a UNIFIED DIFF inside ```diff fences.\n\n"
    "Repo file `{src}` fails tests `{tests}`. Patch `{src}` only.\n\n"
    "Failure tail:\n```\n{failure}\n```"
)


def run_test_cmd(work: Path, tests: list[str]) -> tuple[bool, str]:
    r = subprocess.run(
        ["python3", "-m", "pytest", "-x", "-q", *tests],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    return (r.returncode == 0), (r.stdout + r.stderr)[-1800:]


def record_attempt(record_dir: Path, task: dict, name: str, result: dict, prompt: str, reply: str) -> None:
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / f"{name}.json").write_text(
        json.dumps(
            {
                "task": {k: task[k] for k in ("fix_commit", "parent_commit", "src_file", "test_files")},
                "model": result.get("model"),
                "prompt_hash": sha256(prompt.encode()).hexdigest(),
                "reply_hash": sha256(reply.encode()).hexdigest(),
                "patch_applied": result["patch_applied"],
                "flipped": result["flipped"],
                "usage": result.get("usage", {}),
                "wall_s": result.get("wall_s"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def attempt(work: Path, task: dict, model: str, endpoint: str) -> dict:
    pre_ok, failure = run_test_cmd(work, task["test_files"])
    if pre_ok:
        return {"flipped": False, "patch_applied": False, "precondition": "test already passing", "usage": {}}
    prompt = PROMPT.format(src=task["src_file"], tests=" ".join(task["test_files"]), failure=failure)
    t0 = time.monotonic()
    out = call_model(endpoint, model, prompt)
    wall = time.monotonic() - t0
    diff = extract_diff(out["content"])
    applied = False
    if diff:
        d = work / ".attempt.diff"
        d.write_text(diff)
        ap = subprocess.run(
            ["git", "apply", "--verbose", str(d)], cwd=work, capture_output=True, text=True, check=False
        )
        applied = ap.returncode == 0
    flipped = False
    if applied:
        flipped, _ = run_test_cmd(work, task["test_files"])
    # always restore parent state for the next attempt
    subprocess.run(
        ["git", "checkout", task["parent_commit"], "--", task["src_file"]],
        cwd=work,
        capture_output=True,
        check=False,
    )
    d2 = work / ".attempt.diff"
    if d2.exists():
        d2.unlink()
    return {
        "flipped": flipped,
        "patch_applied": applied,
        "diff_found": diff is not None,
        "usage": out["usage"],
        "wall_s": round(wall, 2),
        "model": out["model"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--repo-path", required=True)
    ap.add_argument("--model", default="moonshotai/Kimi-K3")
    ap.add_argument("--endpoint", default=ENDPOINT)
    ap.add_argument("--n-tasks", type=int, default=3)
    ap.add_argument("--attempts-per-task", type=int, default=1)
    args = ap.parse_args()

    workdir = Path(args.workdir)
    repo = Path(args.repo_path)
    workdir.mkdir(parents=True, exist_ok=True)

    tasks = pick_fix_tasks(repo, n=args.n_tasks)
    print(f"{len(tasks)} tasks")
    results = []
    for task in tasks:
        for i in range(args.attempts_per_task):
            # isolate worktree per task
            work = workdir / "work" / task["fix_commit"][:10]
            if not work.exists():
                sh(["git", "worktree", "add", "--detach", str(work), task["parent_commit"]], cwd=repo)
                for tf in task["test_files"]:
                    sh(["git", "checkout", task["fix_commit"], "--", tf], cwd=work)
            print(f"task {task['fix_commit'][:10]} attempt {i} [{args.model}]...")
            r = attempt(work, task, args.model, args.endpoint)
            r["task"] = task["fix_commit"][:10]
            results.append(r)
            record_attempt(workdir / "records", task, f"{task['fix_commit'][:10]}-{i}", r, prompt=task["src_file"], reply="")

    n_flip = sum(1 for r in results if r.get("flipped"))
    n_ok = sum(1 for r in results if r.get("patch_applied"))
    summary = {
        "model": args.model,
        "tasks": len(tasks),
        "attempts": len(results),
        "applied": n_ok,
        "flips": n_flip,
        "erbve_attempts": 1.0 - n_flip / max(1, len(results)),
    }
    (workdir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
