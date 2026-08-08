#!/usr/bin/env python3
"""Act II pilot — node-side executor: pull SWE-smith image, apply patch, run F2P.

Reads a tasks manifest with patches, executes each inside its task image with
the harness protocol (stop-at-first-valid per act1 design). Writes f2p results.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import os

CAMPAIGN = os.environ.get("PILOT_CAMPAIGN_DIR", "")
BASE = Path(f"/home/ubuntu/latent-imagination/data/landing/act2-pilot/{CAMPAIGN}")
JOBS = BASE / "results"
TASKS = json.loads((BASE / "pilot-tasks.json").read_text())
BY_ID = {t["instance_id"]: t for t in TASKS}


def sh(cmd, cwd=None):
    return subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd,
                          capture_output=True, text=True, check=False)


def run_one(iid: str, arm: str) -> dict:
    d = JOBS / f"{iid.replace('/', '_')}-{arm}"
    meta = json.loads((d / "meta.json").read_text())
    task = BY_ID[iid]
    img = task["image"]
    f2p = task["f2p"]
    box = f"li-pilot-{arm}-{iid.split('.')[0].replace('/', '_')[:20]}"
    sh(["docker", "rm", "-f", box])
    sh(["docker", "pull", img])
    up = sh(["docker", "run", "-d", "--name", box, img, "sleep", "infinity"])
    if up.returncode != 0:
        return {"task": iid, "arm": arm, "error": "docker run failed", "stderr": up.stderr[-300:]}
    try:
        # apply the patch inside the task repo
        repo_dir = sh(["docker", "exec", box, "bash", "-c", "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
        if repo_dir:
            repo = str(Path(repo_dir).parent)
            sh(["docker", "cp", str(d / "patch.diff"), f"{box}:/tmp/patch.diff"])
            gold = JOBS.parent / "control-gold" / iid.replace("/", "_") / "gold.diff"
            sh(["docker", "cp", str(gold), f"{box}:/tmp/bug.diff"])
            bg = sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/bug.diff"])
            meta["bug_applied"] = bg.returncode == 0
            ap = sh(["docker", "exec", box, "git", "-C", repo, "apply", "--verbose", "/tmp/patch.diff"])
            meta["patch_applied"] = ap.returncode == 0 and meta["bug_applied"]
            if not meta["patch_applied"] and meta["bug_applied"]:
                meta["apply_err"] = ap.stderr[-400:]
            if ap.returncode == 0:
                target = task.get("target") or (f2p and "")
                if target:
                    cp = sh(["docker", "exec", box, "/opt/miniconda3/envs/testbed/bin/python",
                             "-m", "py_compile", f"{repo}/{target}"])
                    meta["py_compiles"] = cp.returncode == 0
                    if cp.returncode != 0:
                        meta["py_compile_err"] = cp.stderr[-300:]
            if ap.returncode == 0 and f2p:
                r = sh(["docker", "exec", box, "bash", "-c", f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python -m pytest -x -q {' '.join(f2p[:4])}"])
                meta["f2p_pass"] = r.returncode == 0
                meta["f2p_tail"] = r.stdout[-600:]
                if meta["f2p_pass"] and task.get("p2p"):  # régression-check uniquement sur les vrais succès
                    rp = sh(["docker", "exec", box, "bash", "-c",
                             f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python -m pytest -q {' '.join(task['p2p'][:30])}"])
                    meta["p2p_pass"] = rp.returncode == 0
                    meta["p2p_tail"] = (rp.stdout + rp.stderr)[-300:]
                p2p = task.get("p2p") or []
                if meta["f2p_pass"] and p2p:  # régression-check uniquement sur les slots verts
                    rr = sh(["docker", "exec", box, "bash", "-c",
                             f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python -m pytest -q {' '.join(p2p[:20])}"])
                    meta["p2p_pass"] = rr.returncode == 0
                    meta["p2p_tail"] = (rr.stdout + rr.stderr)[-400:]
    finally:
        sh(["docker", "rm", "-f", box])
    return meta


def main():
    for task in TASKS:
        iid = task["instance_id"]
        for arm in ("off", "on"):
            d = JOBS / f"{iid.replace('/', '_')}-{arm}"
            if not (d / "patch.diff").exists():
                continue
            r = run_one(iid, arm)
            (d / "run-result.json").write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
            print(iid[:40], arm, r.get("f2p_pass"), r.get("patch_applied"))


if __name__ == "__main__":
    main()
