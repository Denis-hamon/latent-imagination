#!/usr/bin/env python3
"""Extrait la source POST-BUG (gold patch applied, avant le fix agent).

Règle méthodologique act2 révisée 2026-08-07 : la colonne `patch` des parquets
swe-smith est le commit qui INTRODUIT le bug. L'image docker contient le code
d'origine (les F2P y passent). L'agent doit donc toujours partir de la version
infectée, sinon le prompt ment ("failing tests" sur une base qui passe).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

WOOD = Path(__file__).resolve().parents[2]
JOBS = WOOD / "data" / "landing" / "act2-pilot"
TASKS = JOBS / "pilot-tasks.json"
GOLD = JOBS / "control-gold"


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900)


def run_one(task: dict) -> dict:
    iid = task["instance_id"]
    gold = GOLD / iid.replace("/", "_") / "gold.diff"
    img = task["image"]
    target = task.get("target")  # fichier touché par le bug (extrait du gold)
    box = f"li-bug-{iid.split('.')[0][:24].replace('/', '_')}"
    sh(["docker", "rm", "-f", box])
    up = sh(["docker", "run", "-d", "--name", box, img, "sleep", "600"])
    if up.returncode != 0:
        return {"task": iid, "error": "docker run failed", "stderr": up.stderr[-200:]}
    try:
        repo_dir = sh(["docker", "exec", box, "bash", "-c",
                       "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
        repo = str(Path(repo_dir).parent) if repo_dir else "/testbed"
        sh(["docker", "cp", str(gold), f"{box}:/tmp/bug.diff"])
        ap = sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/bug.diff"])
        if ap.returncode != 0:
            return {"task": iid, "error": "bug-apply failed", "stderr": ap.stderr[-300:]}
        # control : F2P must fail now
        t = " ".join(task["f2p"][:4])
        r = sh(["docker", "exec", box, "bash", "-c",
                f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python -m pytest -x -q {t}"])
        f2p_rc = r.returncode
        # export the buggy source
        key = iid.split(".")[0].replace("/", "_")
        rc = sh(["docker", "exec", box, "cat", f"{repo}/{target}"])
        (JOBS / f"{iid.split('__')[0][:6]}-{task['src_key']}.buggy.py").write_text(rc.stdout)
        return {"task": iid, "bug_applied": True, "f2p_after_bug_rc": f2p_rc,
                "buggy_src_path": target,
                "f2p_tail": (r.stdout + r.stderr)[-400:]}
    finally:
        sh(["docker", "rm", "-f", box])


def main() -> int:
    tasks = json.loads(TASKS.read_text())
    out = []
    for t in tasks:
        r = run_one(t)
        out.append(r)
        v = "OK bug-injecté, F2P échouent" if r.get("f2p_after_bug_rc") not in (0, None) else "?! F2P passent malgré le bug"
        print(f"{t['instance_id'][:44]:44} {v}")
    (JOBS / "buggy-state.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
