#!/usr/bin/env python3
"""Contrôle négatif act2 : pour chaque tâche du pilote, exécute les tests F2P
dans l'image docker SANS appliquer de patch. Attendu : échec (sinon la mesure
F2P est sans valeur — le test ne change pas d'état)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

WOOD = Path(__file__).resolve().parents[2]
JOBS = WOOD / "data" / "landing" / "act2-pilot"
TASKS = JOBS / "pilot-tasks.json"


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900)


def run_one(task: dict) -> dict:
    iid = task["instance_id"]
    img = task["image"]
    f2p = task["f2p"]
    box = f"li-ctrl-{iid.split('.')[0][:24].replace('/', '_')}"
    sh(["docker", "rm", "-f", box])
    up = sh(["docker", "run", "-d", "--name", box, img, "sleep", "600"])
    if up.returncode != 0:
        return {"task": iid, "control": "docker-failed", "stderr": up.stderr[-200:]}
    try:
        repo_dir = sh(["docker", "exec", box, "bash", "-c",
                       "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
        repo = str(Path(repo_dir).parent) if repo_dir else "/testbed"
        tests = " ".join(f2p[:4])
        r = sh(["docker", "exec", box, "bash", "-c",
                f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python -m pytest -x -q {tests}"])
        return {"task": iid, "repo": repo, "tests": tests,
                "rc": r.returncode, "tail": (r.stdout + r.stderr)[-600:]}
    finally:
        sh(["docker", "rm", "-f", box])


def main() -> int:
    tasks = json.loads(TASKS.read_text())
    out = []
    for t in tasks:
        r = run_one(t)
        out.append(r)
        verdict = "FAIL (attendu)" if r.get("rc") not in (0, None) else "PASS (?!)" if r.get("rc") == 0 else r.get("control", "?")
        print(f"{t['instance_id'][:44]:44} rc={r.get('rc')!r:5} → {verdict}")
    (JOBS / "control-baseline.json").write_text(
        json.dumps(out, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
