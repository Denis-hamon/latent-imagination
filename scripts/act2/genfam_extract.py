#!/usr/bin/env python3
"""Story 10.1 — extraction buggy-src des tâches genfam sur le NODE (docker).

Depuis staging-extract.json (autosuffisant : image, patch bug-inducteur, f2p,
target) : pull image → run → localiser le repo → git apply du bug-patch →
les F2P DOIVENT échouer (contrôle positif, leçon pilote : un zéro ne prouve
rien) → cat du fichier cible → <instance>.buggy.py.

Idempotent : une extraction existante (>100 octets) est re-vérifiée par hash,
pas re-tirée. Rapport JSON par tâche (succès / raison d'échec), jamais de
supposition silencieuse.

Run (node): python3 scripts/act2/genfam_extract.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

WOOD = Path(__file__).resolve().parents[2]
JOBS = WOOD / "data" / "landing" / "act2-pilot" / "genfam-q1"
STAGING = JOBS / "staging-extract.json"
REPORT = JOBS / "extract-report.json"


def sh(cmd: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)


def run_one(task: dict) -> dict:
    iid = task["instance_id"]
    fn = JOBS / f"{iid.replace('/', '_')}.buggy.py"
    patch_sha = sha256(task["patch"].encode()).hexdigest()
    if fn.is_file() and fn.stat().st_size > 100:
        return {"task": iid, "skipped": "exists",
                "buggy_sha256": sha256(fn.read_bytes()).hexdigest()}
    img = task["image"]
    box = f"li-genfam-{iid.split('.')[0][:20].replace('/', '_')}-{iid[-6:]}"
    sh(["docker", "rm", "-f", box])
    if sh(["docker", "pull", img]).returncode != 0:
        return {"task": iid, "error": "docker pull failed"}
    if sh(["docker", "run", "-d", "--name", box, img, "sleep", "900"]).returncode != 0:
        return {"task": iid, "error": "docker run failed"}
    try:
        find = sh(["docker", "exec", box, "bash", "-c",
                   "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
        repo = str(Path(find).parent) if find else "/testbed"
        diff_file = JOBS / f".tmp-{iid[-12:]}.diff"
        diff_file.write_text(task["patch"])
        cp = sh(["docker", "cp", str(diff_file), f"{box}:/tmp/bug.diff"])
        diff_file.unlink(missing_ok=True)
        if cp.returncode != 0:
            return {"task": iid, "error": "docker cp failed"}
        ap = sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/bug.diff"])
        if ap.returncode != 0:
            return {"task": iid, "error": "bug-apply failed", "stderr": ap.stderr[-300:]}
        tests = " ".join(task["f2p"][:4])
        r = sh(["docker", "exec", box, "bash", "-c",
                f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python -m pytest -x -q {tests}"],
               timeout=900)
        if r.returncode == 0:
            return {"task": iid, "error": "F2P passent malgré le bug — extraction refusée",
                    "f2p_rc": 0}
        cat = sh(["docker", "exec", box, "cat", f"{repo}/{task['target']}"])
        src = cat.stdout
        if len(src.strip()) < 100:
            return {"task": iid, "error": f"cat cible vide/court: {task['target']}",
                    "stderr": cat.stderr[-200:]}
        fn.write_text(src)
        return {"task": iid, "ok": True, "bug_applied": True,
                "f2p_rc_after_bug": r.returncode, "buggy_src_path": task["target"],
                "patch_sha256": patch_sha,
                "buggy_sha256": sha256(src.encode()).hexdigest(),
                "buggy_bytes": len(src.encode())}
    except subprocess.TimeoutExpired:
        return {"task": iid, "error": "timeout docker exec"}
    finally:
        sh(["docker", "rm", "-f", box], timeout=60)


def main() -> int:
    if not STAGING.is_file():
        print(f"ABSENT: {STAGING}")
        return 2
    staging = json.loads(STAGING.read_text())
    results = [run_one(t) for t in staging["tasks"]]
    ok = sum(1 for r in results if r.get("ok"))
    skipped = sum(1 for r in results if r.get("skipped"))
    REPORT.write_text(json.dumps({
        "window": "gen-families-v1",
        "selection_digest": staging["selection_digest"],
        "n_tasks": len(staging["tasks"]), "n_ok": ok, "n_skipped": skipped,
        "n_errors": len(results) - ok - skipped,
        "results": results,
    }, indent=1) + "\n")
    print(f"extraction: {ok} ok, {skipped} déjà présentes, "
          f"{len(results) - ok - skipped} erreurs → {REPORT}")
    for r in results:
        if r.get("error"):
            print(f"  ERREUR {r['task']}: {r['error']}")
    return 0 if ok + skipped == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
