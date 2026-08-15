#!/usr/bin/env python3
"""Contrôle positif act2 : applique le GOLD patch dans l'image docker puis
exécute les F2P. Attendu : PASS. Si ça rate, le harness Sphinx est borgne
dans l'autre sens — les tests qu'on cible ne sont pas exécutables tels quels
dans leurs images."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

WOOD = Path(__file__).resolve().parents[2]
JOBS = WOOD / "data" / "landing" / "act2-pilot"
TASKS = JOBS / "pilot-tasks.json"
GOLDS = JOBS / "control-gold"


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=False)  # callers inspect rc


def run_one(task: dict) -> dict:
    iid = task["instance_id"]
    gold = GOLDS / iid.replace("/", "_") / "gold.diff"
    if not gold.is_file():
        return {"task": iid, "control": "no-gold-patch"}
    img = task["image"]
    f2p = task["f2p"]
    box = f"li-gold-{iid.split('.')[0][:24].replace('/', '_')}"
    sh(["docker", "rm", "-f", box])
    up = sh(["docker", "run", "-d", "--name", box, img, "sleep", "600"])
    if up.returncode != 0:
        return {"task": iid, "control": "docker-failed", "stderr": up.stderr[-200:]}
    try:
        repo_dir = sh(["docker", "exec", box, "bash", "-c",
                       "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
        repo = str(Path(repo_dir).parent) if repo_dir else "/testbed"
        sh(["docker", "cp", str(gold), f"{box}:/tmp/gold.diff"])
        ap = sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/gold.diff"])
        t = " ".join(f2p[:4])
        r = sh(["docker", "exec", box, "bash", "-c",
                f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python -m pytest -x -q {t}"])
        return {"task": iid, "gold_apply_rc": ap.returncode,
                "gold_apply_err": ap.stderr[-300:] if ap.returncode else "",
                "f2p_rc": r.returncode, "tail": (r.stdout + r.stderr)[-500:]}
    finally:
        sh(["docker", "rm", "-f", box])


def main() -> int:
    tasks = json.loads(TASKS.read_text())
    out = []
    for t in tasks:
        r = run_one(t)
        out.append(r)
        v = ("PASS ✓" if r.get("f2p_rc") == 0 else
             f"FAIL (apply rc={r.get('gold_apply_rc')}, f2p rc={r.get('f2p_rc')})")
        print(f"{t['instance_id'][:44]:44} {v}")
    (JOBS / "control-gold.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
