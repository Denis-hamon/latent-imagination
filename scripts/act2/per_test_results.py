#!/usr/bin/env python3
"""Capture node-side des résultats par test F2P (multi-hot Yu-auxiliaire).

Pour chaque slot appliqué (results + extension-128/results) où patch_applied :
re-run complet docker avec bug injecté + patch, puis chaque test F2P séparément,
avec la classe d'erreur extraite (importation, nameerror, assert, ...).

Sortie : data/landing/act2-pilot/per-test.json
[task/arm] -> [{'test': ..., 'passed': bool, 'errclass': str}]
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot")
OUT = ROOT / "per-test.json"


def sh(cmd, timeout=900):
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)


ERR_PAT = re.compile(r"(ImportError|ModuleNotFoundError|NameError|AttributeError|SyntaxError|IndentationError|TypeError|ValueError|AssertionError|KeyError|IndexError|RecursionError|TimeoutError)")


def errclass(text: str) -> str:
    m = ERR_PAT.findall(text)
    return m[-1] if m else "PASS" if "passed" in text else "unknown"


def run_one(box_base: str, img: str, gold: Path, patch: Path, f2p: list[str]) -> list[dict]:
    box = box_base
    sh(["docker", "rm", "-f", box])
    up = sh(["docker", "run", "-d", "--name", box, img, "sleep", "900"])
    if up.returncode != 0:
        return [{"test": "<docker>", "passed": False, "errclass": "docker-failed"}]
    try:
        repo_dir = sh(["docker", "exec", box, "bash", "-c",
                       "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
        repo = str(Path(repo_dir).parent) if repo_dir else "/testbed"
        sh(["docker", "cp", str(gold), f"{box}:/tmp/bug.diff"])
        sh(["docker", "cp", str(patch), f"{box}:/tmp/p.diff"])
        b1 = sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/bug.diff"])
        b2 = sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/p.diff"])
        if b1.returncode != 0 or b2.returncode != 0:
            return [{"test": "<apply>", "passed": False, "errclass": "apply-failed"}]
        out = []
        for t in f2p[:4]:
            r = sh(["docker", "exec", box, "bash", "-c",
                    f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python -m pytest -q {t} 2>&1 | tail -6"])
            text = r.stdout + r.stderr
            out.append({"test": t, "passed": r.returncode == 0, "errclass": errclass(text)})
        return out
    finally:
        sh(["docker", "rm", "-f", box])


def main() -> int:
    all_rows: dict[str, list] = {}
    for campaign in ("", "extension-128"):
        base = ROOT / campaign
        pdir = base / "results"
        if not pdir.is_dir():
            continue
        tasks = {t["instance_id"]: t for t in json.loads((base / "pilot-tasks.json").read_text())}
        for d in sorted(pdir.glob("*")):
            mf, pf, rf = d / "meta.json", d / "patch.diff", d / "run-result.json"
            if not (mf.is_file() and pf.is_file() and rf.is_file()):
                continue
            if not pf.read_text().strip():
                continue
            m = json.loads(mf.read_text())
            r = json.loads(rf.read_text())
            if not r.get("patch_applied"):
                continue
            t = tasks[m["task"]]
            gold = base / "control-gold" / m["task"].replace("/", "_") / "gold.diff"
            key = f"{campaign or 'frozen32'}|{m['task']}|{m['arm']}"
            rows = run_one(f"li-pt-{abs(hash(key)) % 99999}", t["image"], gold, pf, t["f2p"])
            all_rows[key] = rows
            npass = sum(1 for x in rows if x["passed"])
            print(key[:62], f"{npass}/{len(rows)}", flush=True)
    OUT.write_text(json.dumps(all_rows, indent=1))
    print("total slots:", len(all_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
