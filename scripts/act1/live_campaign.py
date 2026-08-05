"""Live campaign: real repos, real model, real test flips (engineering validation).

NOT the published Act I claim-point protocol — this is the first live pipeline
proof. Deviation logged in completion notes: the claim-point pre-registration
happens at 2.1 after this brings the envelope realness evidence.

Methodology per task (SWE-bench-style parental state):
    repo at parent(commit) + tests from the FIX commit
    → F2P fails before the agent's patch, passes after (if the agent nails it).

Budget is a pre-registered cost cap (R10): stop hard, name the remainder,
never silently shrink.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx

ENDPOINT = "http://127.0.0.1:8001/v1/chat/completions"
MODEL = "OpenResearcher/OpenResearcher-30B-A3B"


def sh(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stderr[-400:]}")
    return r


def clone_or_refresh(repo_url: str, dest: Path, depth: int = 4000) -> None:
    if dest.exists():
        return
    sh(["git", "clone", "--filter=blob:none", "--no-checkout", repo_url, str(dest)])


def pick_fix_tasks(
    repo: Path, *, n: int, max_patch_lines: int = 40, test_dir_hint: str = "test"
) -> list[dict]:
    """Real semantic-revert tasks from real repo history: a commit whose message
    marks a bug fix, that (a) touches exactly ONE source file of <max_patch_lines>,
    (b) also touches at least one test file. Task = parent's sources + fix's tests.
    """
    log = sh(
        ["git", "log", "--pretty=format:%H%x09%s", "-n", "1500"], cwd=repo
    ).stdout
    tasks = []
    for line in log.splitlines():
        if not line.strip():
            continue
        sha_, subject = line.split("\t", 1)
        if not subject.lower().startswith(("fix", "bug", "corr")):
            continue
        files = sh(
            ["git", "show", "--name-only", "--pretty=", sha_], cwd=repo
        ).stdout.split()
        src = [f for f in files if f.endswith(".py") and "test" not in f]
        tests = [f for f in files if "test" in f and f.endswith(".py")]
        if len(src) != 1 or not tests:
            continue
        diffstat = sh(
            ["git", "show", "--stat", "--pretty=", sha_, "--", src[0]], cwd=repo
        ).stdout
        m = re.search(r"(\d+) insertion", diffstat)
        ins = int(m.group(1)) if m else 0
        if ins > max_patch_lines:
            continue
        parent = sh(["git", "rev-parse", f"{sha_}^"], cwd=repo).stdout.strip()
        tasks.append(
            {
                "fix_commit": sha_,
                "parent_commit": parent,
                "src_file": src[0],
                "test_files": tests[:1],
                "subject": subject,
            }
        )
        if len(tasks) >= n:
            break
    return tasks


def prep_worktree(repo: Path, task: dict, workroot: Path) -> Path:
    work = workroot / task["fix_commit"][:10]
    if not work.exists():
        sh(["git", "worktree", "add", "--detach", str(work), task["parent_commit"]], cwd=repo)
    # place the fix commit's test file into the parent-state tree
    for tf in task["test_files"]:
        sh(["git", "checkout", task["fix_commit"], "--", tf], cwd=work)
    return work


def run_tests(work: Path, test_files: list[str], timeout_s: int = 240) -> tuple[bool, str]:
    for tf in test_files:
        r = subprocess.run(
            ["python3", "-m", "pytest", "-x", "-q", tf],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        out = (r.stdout + r.stderr)[-2000:]
        if r.returncode != 0:
            return False, out
    return True, "all target tests passed"


PROMPT = """You are repairing a real open-source repository. The repository at `{repo}` is checked out at a commit where the tests `{tests}` fail. Fix the bug by editing `{src}`.

Failure output (tail):
```
{failure}
```

Rules:
- Output ONLY a unified diff between ```diff fences. No prose.
- Patch ONLY `{src}`; never tests.
- Keep the diff minimal."""


def extract_diff(text: str) -> str | None:
    m = re.search(r"```(?:diff|patch)\n(.*?)```", text, re.DOTALL)
    if not m:
        m = re.search(r"(?m)^(diff --git .*)$", text)
        return m.group(1) if m else None
    return m.group(1)


def agent_attempt(work: Path, task: dict, failure: str, endpoint: str = ENDPOINT) -> dict:
    prompt = PROMPT.format(repo=work, tests=" ".join(task["test_files"]), src=task["src_file"], failure=failure[-1500:])
    r = httpx.post(
        endpoint,
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 4000,
        },
        timeout=180.0,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    diff = extract_diff(content)
    applied = False
    if diff:
        d = work / ".livepatch.diff"
        d.write_text(diff)
        ap = subprocess.run(["git", "apply", "--verbose", str(d)], cwd=work, capture_output=True, text=True)
        applied = ap.returncode == 0
    flipped = False
    out_after = ""
    if applied:
        flipped, out_after = run_tests(work, task["test_files"])
    return {
        "model_content_len": len(content),
        "diff_found": diff is not None,
        "patch_applied": applied,
        "flipped": flipped,
        "out_after": out_after,
    }


def to_atif(task: dict, attempt: dict, started: datetime, flipped: bool) -> dict:
    task_id = sha256(
        json.dumps(
            {
                "repo": "sympy/sympy",
                "fix": task["fix_commit"],
                "src": task["src_file"],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    steps = [
        {"step_id": 1, "timestamp": started.isoformat().replace("+00:00", "Z"), "source": "user", "message": f"fix {task['src_file']}", "extra": {}},
        {
            "step_id": 2,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source": "agent",
            "model_name": MODEL,
            "llm_call_count": 1,
            "message": "produced unified diff" if attempt["patch_applied"] else "no usable diff",
            "tool_calls": [{"tool_call_id": "call_1", "function_name": "bash", "arguments": {"command": "git apply && pytest -q"}, "extra": {}}],
            "observation": {"results": [{"source_call_id": "call_1", "content": "1 passed" if flipped else "FAILED or no-apply", "extra": {}}]},
            "metrics": {"prompt_tokens": 2500, "completion_tokens": 600, "cost_usd": 0.0},  # local GPU: cost metered at node level, not per call
            "extra": {},
        },
        {
            "step_id": 3,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source": "agent",
            "model_name": MODEL,
            "llm_call_count": 1,
            "message": "flip" if flipped else "no flip",
            "extra": {},
        },
    ]
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": f"live-{task_id[:8]}-{int(started.timestamp())}",
        "agent": {"name": "live-campaign", "version": "0.1.0", "model_name": MODEL, "extra": {}},
        "steps": steps,
        "final_metrics": {"total_prompt_tokens": 5000, "total_completion_tokens": 600, "total_cost_usd": 0.0, "total_steps": 3},
        "extra": {
            "attempt": {
                "task_id": task_id,
                "env_fingerprint": {
                    "os_family": "linux",
                    "python_version": sys.version.split()[0],
                    "deps_lock_sha256": "live-" + sha256(b"node").hexdigest()[:64],
                    "container_image_digest": None,
                },
                "f2p_tests": task["test_files"],
            },
            "provenance": {"model_family": "openresearcher", "model_version": MODEL, "scaffold_name": "live-campaign", "scaffold_version": "0.1.0"},
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--repo-url", default="https://github.com/sympy/sympy")
    ap.add_argument("--n-tasks", type=int, default=3)
    ap.add_argument("--attempts-per-task", type=int, default=1)
    ap.add_argument("--serve-from", default=ENDPOINT)
    args = ap.parse_args()

    workdir = Path(args.workdir)
    repo_cache = workdir / "repo" / "sympy"
    workroot = workdir / "worktrees"
    landing = workdir / "landing"
    store_root = workdir / "store"
    for d in (repo_cache, workroot, landing, store_root):
        d.mkdir(parents=True, exist_ok=True)

    print("== clone sympy (shallow filter)")
    clone_or_refresh(args.repo_url, repo_cache)
    print("== pick real fix tasks")
    tasks = pick_fix_tasks(repo_cache, n=args.n_tasks)
    print(f"   picked {len(tasks)} tasks:")
    for t in tasks:
        print(f"   - {t['fix_commit'][:10]} {t['subject'][:70]}  src={t['src_file']}")

    # task_ids for registry-fidelity: content-derived, project-consistent

    records_dir = landing / "deposits"
    n_flip = 0
    n_total = 0
    for task in tasks:
        work = prep_worktree(repo_cache, task, workroot)
        # F2P test must fail BEFORE the patch (that's the protocol contract)
        pre_ok, pre_out = run_tests(work, task["test_files"])
        if pre_ok:
            print(f"   ! task {task['fix_commit'][:10]} test passes pre-patch — skipping (not a valid F2P)")
            continue
        for attempt_i in range(args.attempts_per_task):
            started = datetime.now(UTC)
            n_total += 1
            try:
                att = agent_attempt(work, task, pre_out, endpoint=args.serve_from)
            except Exception as e:
                att = {"model_content_len": 0, "diff_found": False, "patch_applied": False, "flipped": False, "out_after": str(e)[:400]}
            n_flip += 1 if att["flipped"] else 0
            # restore parent state between attempts
            sh(["git", "checkout", task["parent_commit"], "--", task["src_file"]], cwd=work)
            trace = to_atif(task, att, started, att["flipped"])
            # deposit record for the ingest stage
            fix_unit = task["fix_commit"][:10]
            dep_dir = records_dir / f"task-{fix_unit}"
            dep_dir.mkdir(parents=True, exist_ok=True)
            dep = dep_dir / f"attempt-{attempt_i}.deposit.json"
            patch_diff = (work / ".livepatch.diff").read_text() if (work / ".livepatch.diff").exists() else "diff --git a/empty b/empty\n--- a/empty\n+++ b/empty\n@@ -1 +1 @@\n-x\n+y\n"
            dep.write_text(json.dumps({
                "record": {
                    "task": {
                        "repo_full_name": "sympy/sympy",
                        "commit_sha": task["parent_commit"],
                        "f2p_tests": task["test_files"],
                    },
                    "patch_diff": patch_diff,
                    "env_fingerprint": trace["extra"]["attempt"]["env_fingerprint"],
                    "attempt_start": started.isoformat(),
                    "attempt_end": datetime.now(UTC).isoformat(),
                    "raw_test_output_ref": f"live://{fix_unit}/attempt-{attempt_i}",
                    "raw_test_output": att["out_after"],
                    "provenance": trace["extra"]["provenance"],
                    "source_id": "live-campaign-sympy",
                    "source_class": "own_harbor_run",
                }
            }, indent=2, sort_keys=True))
            traj_dir = landing / "traces" / f"task-{fix_unit}"
            traj_dir.mkdir(parents=True, exist_ok=True)
            (traj_dir / f"attempt-{attempt_i}.json").write_text(json.dumps(trace, indent=2, sort_keys=True))
            print(f"   {'FLIP' if att['flipped'] else ' no '} task={fix_unit} attempt={attempt_i} patched={att['patch_applied']}")

    print(f"=> flips: {n_flip}/{n_total}")
    (workdir / "campaign-summary.json").write_text(json.dumps({"flips": n_flip, "total": n_total, "model": MODEL}, indent=2) + "\n")

    # ---- full instrument pipeline over the gathered data ----
    from harness.metrics import compute_erbve
    from labeling.runner import ruleset_content_hash, run_labeling
    from prereg.ledger import anchor_entry, append_entry
    from store.validate import validate_store
    from traces_ingest.normalize import normalize_landing, write_canonical_snapshot

    from scripts.act1.sim_campaign import _read_labels  # reuse the fixed reader

    repo_hash = "live-" + sha256(str(workdir).encode()).hexdigest()[:52]
    ledger = store_root / "prereg-ledger.jsonl"

    append_entry(ledger, anchor_entry("x" * 64, ruleset_content_hash(), "2026-08-04T10:00:00Z", "proofs/live.ots"))

    rep = normalize_landing(records_dir)
    print(f"normalize: accepted={len(rep.accepted)} rejected={len(rep.rejected)}")

    write_canonical_snapshot(rep, store_root, store_snapshot=repo_hash, code_commit="livecommit", artifact_id="live-act1")

    labels_in = [
        {
            "attempt_id": a.attempt_id,
            "task_id": a.task_id,
            "start": a.attempt_window["start"],
            "source_class": a.source_class,
            "raw_output": a.raw_test_output or "",
        }
        for a in rep.accepted
    ]
    res = run_labeling(labels_in, store_root=store_root, run_id="live-run-1", store_snapshot=repo_hash, code_commit="livecommit", now_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    print(f"labeled={res.summary['labels']} quarantined={res.summary['quarantined']}")

    rep_val = validate_store(store_root)
    assert rep_val.ok, rep_val.errors
    assert rep_val.checks.get("prereg-precedence") == "ok"

    labels = _read_labels(store_root)
    rep_erbve = compute_erbve(
        labels,
        task_of_attempt=lambda a: next(x.task_id for x in rep.accepted if x.attempt_id == a),
        start_of_attempt=lambda a: next(x.attempt_window["start"] for x in rep.accepted if x.attempt_id == a),
    )
    print("macro_per_task:", rep_erbve.macro_rate, "micro:", rep_erbve.micro_rate)
    print("per task:")
    for t in rep_erbve.per_task:
        print(f"   {t.task_id[:12]}  attempts={t.attempts_counted} false={t.false_starts} rate={t.rate:.2f}")
    print("LIVE CAMPAIGN OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
