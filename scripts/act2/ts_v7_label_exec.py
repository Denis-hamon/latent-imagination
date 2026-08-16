#!/usr/bin/env python3
"""Window coverage-ts-v7 — labellisation distante VITEST multi-sources (zod +
date-fns) sur Kimsufi-standard. rules-v1 : y=1 <=> F2P reverdissent ET (P2P
vertes OU P2P non déclarées). Pose du diff : git apply --recount puis patch -l
--fuzz=3 (leçon v2), SHA du fichier cible vérifiée AVANT/APRÈS application —
le verdict de pose est le sha, jamais le rc. Worktree sérialisé, restauration
git après chaque slot.
Run: uv run python scripts/act2/ts_v7_label_exec.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "coverage-ts-7"
RESULTS = Q / "gen-results"
STAGING = Q / "staging-extract.json"
HOST = "Kimsufi-standard"

RUNNERS = {
    "zod": {"remote": "~/zod-source",
            "cmd": "cd ~/zod-source && npx vitest run --reporter=tap {spec} 2>&1"},
    "date-fns": {"remote": "~/date-fns-source",
                 "cmd": "cd ~/date-fns-source/pkgs/core && npx vitest run --reporter=tap {spec} 2>&1"},
}


def sh_local(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def sh_remote(cmd: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return sh_local(["ssh", "-o", "ConnectTimeout=12", HOST, cmd], timeout=timeout)


def parse_tap(text: str, repo: str) -> list[str]:
    """Noms des tests non-ok en FEUILLE (zod : indent 4 ; date-fns : >=8 sans
    accolade finale)."""
    failed = []
    for line in text.splitlines():
        if repo == "zod":
            if line.startswith("    not ok ") and not line.rstrip().endswith("{"):
                failed.append(line.strip()[7:].split(" # ")[0].strip())
        else:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if indent >= 8 and stripped.startswith("not ok ") and not line.rstrip().endswith("{"):
                failed.append(stripped[7:].split(" # ")[0].strip())
    return failed


def count_pass(text: str, repo: str) -> int:
    n = 0
    for line in text.splitlines():
        if repo == "zod":
            if line.startswith("    ok ") and not line.rstrip().endswith("{"):
                n += 1
        else:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if indent >= 8 and stripped.startswith("ok ") and not line.rstrip().endswith("{"):
                n += 1
    return n


def _check_clean(remote: str) -> bool:
    return not sh_remote(f"cd {remote} && git status --porcelain | head -1").stdout.strip()


def run_slot(slot_dir: Path, task: dict) -> dict:
    repo = task["repo"]
    spec = task["spec"]
    iid = task["instance_id"]
    runner = RUNNERS[repo]
    out: dict = {"task": iid, "slot": slot_dir.name, "campaign": "coverage-ts-7",
                 "window": "coverage-ts-v7", "repo": repo,
                 "labeled_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    try:
        if not _check_clean(runner["remote"]):
            out["error"] = "worktree non propre avant labellisation"
            return out
        buggy = Q / f"{iid.replace('/', '_')}.buggy.py"
        if not buggy.is_file():
            out["error"] = "buggy source absente"
            return out
        target = task["target"]  # chemin relatif AU repo (quota: file_prefix préfixé)
        up = sh_local(["scp", "-q", str(buggy), f"{HOST}:{runner['remote']}/{target}"], timeout=120)
        if up.returncode != 0:
            out["error"] = "scp buggy échoué"
            return out
        r0 = sh_remote(runner["cmd"].format(spec=spec), timeout=600)
        out["f2p_red_after_bug"] = parse_tap(r0.stdout, repo)
        out["p2p_after_bug_n"] = count_pass(r0.stdout, repo)
        diff = slot_dir / "diff.patch"
        if not diff.is_file():
            out["error"] = "diff absent"
            return out
        sh_local(["scp", "-q", str(diff), f"{HOST}:/tmp/genfam-cand.diff"], timeout=120)
        sha_pre = sh_remote(f"sha256sum {runner['remote']}/{target} | cut -c1-64").stdout.strip()
        sh_remote(f"cd {runner['remote']} && git apply --recount /tmp/genfam-cand.diff 2>&1")
        sha_post = sh_remote(f"sha256sum {runner['remote']}/{target} | cut -c1-64").stdout.strip()
        mode = "strict-git" if sha_post != sha_pre else None
        if mode is None:
            sh_remote(f"cd {runner['remote']} && patch -p1 -l --fuzz=3 -s < /tmp/genfam-cand.diff 2>&1")
            sha_post = sh_remote(f"sha256sum {runner['remote']}/{target} | cut -c1-64").stdout.strip()
            mode = "fuzz" if sha_post != sha_pre else None
        out["patch_applied"] = mode is not None
        out["apply_mode"] = mode
        if mode is None:
            out["label"] = None
            out["note"] = "diff inapplicable = pas de réparation produite"
            return out
        r1 = sh_remote(runner["cmd"].format(spec=spec), timeout=600)
        failed_after = parse_tap(r1.stdout, repo)
        passed_after = count_pass(r1.stdout, repo)
        declared = set(task.get("f2p", []))
        f2p_still_red = [t for t in failed_after if t in declared or t in out.get("f2p_red_after_bug", [])]
        out["f2p_rc"] = 1 if f2p_still_red else 0
        p2p_failed = [t for t in failed_after if t not in declared] if declared else failed_after
        out["p2p_rc"] = 0 if not p2p_failed else 1
        out["f2p_still_red"] = f2p_still_red[:8]
        out["p2p_failed"] = p2p_failed[:4]
        out["passed_after"] = passed_after
        if out["f2p_rc"] == 0 and out["p2p_rc"] == 0:
            out["y"] = 1
        elif out["f2p_rc"] == 0 and out["p2p_rc"] == 1:
            out["y"] = "quarantaine-p2p"
        else:
            out["y"] = 0
        return out
    finally:
        runner_remote = RUNNERS[repo]["remote"]
        sh_remote(f"cd {runner_remote} && git checkout -- . && rm -f /tmp/genfam-cand.diff", timeout=120)
        if not _check_clean(runner_remote):
            out.setdefault("cleanup_warning", "restauration remote à vérifier")


def main() -> int:
    staging = json.loads(STAGING.read_text())
    by_iid = {t["instance_id"]: t for t in staging["tasks"]}
    slots = []
    for sd in sorted(RESULTS.glob("*-d*")):
        rf = sd / "rec.json"
        if rf.is_file() and json.loads(rf.read_text()).get("status") == "ok":
            slots.append(sd)
    done = run = errors = 0
    for sd in slots:
        if (sd / "run-result.json").is_file():
            done += 1
            continue
        task = by_iid.get(json.loads((sd / "rec.json").read_text())["task"])
        if task is None:
            errors += 1
            continue
        r = run_slot(sd, task)
        (sd / "run-result.json").write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
        run += 1
        errors += 1 if r.get("error") else 0
        print(f"{sd.name[:58]:58} y={r.get('y')} mode={r.get('apply_mode')} "
              f"f2p_rc={r.get('f2p_rc')} p2p_rc={r.get('p2p_rc')}"
              + (f" ERR={r.get('error')}" if r.get("error") else ""), flush=True)
    print(f"\n== TSv7-L : {done} déjà mesurés, {run} exécutés, {errors} erreurs ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
