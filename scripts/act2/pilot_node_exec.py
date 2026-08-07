#!/usr/bin/env python3
"""Act II pilot — node-side executor: pull SWE-smith image, apply patch, run F2P.

Reads a tasks manifest with patches, executes each inside its task image with
the harness protocol (stop-at-first-valid per act1 design). Writes f2p results.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

JOBS = Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot/results")
TASKS = json.loads(Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot/pilot-tasks.json").read_text())
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
            ap = sh(["docker", "exec", box, "git", "-C", repo, "apply", "--verbose", "/tmp/patch.diff"])
            meta["patch_applied"] = ap.returncode == 0
            if ap.returncode == 0 and f2p:
                r = sh(["docker", "exec", box, "bash", "-c", f"cd {repo} && python -m pytest -x -q {' '.join(f2p[:4])}"])
                meta["f2p_pass"] = r.returncode == 0
                meta["f2p_tail"] = r.stdout[-600:]
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
