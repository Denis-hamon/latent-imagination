#!/usr/bin/env python3
"""Story coverage-ts-v10 — labellisation DISTANTE triple-runner (omniroute node:test / zod+date-fns vitest).

Chaîne identique en discipline à ts14_label_exec (locale acre), adaptée au
serveur : le fichier buggy est POSÉ par scp sur la cible (pas de git-apply du
bug : le contenu buggy EST l'état infecté, vérifié à la construction du
quota), puis :
  worktree propre exigé → scp buggy → contrôle positif : F2P DOIVENT échouer →
  git apply diff candidat (strict) → vitest spec complet → F2P (nommés) +
  autres tests = P2P → restauration git (finally, arbre propre vérifié).

Zéro juge : labels = sorties vitest ; raw tails conservés (FR-3). Sérialisé
(un slot à la fois, jamais de mutation concurrente du worktree).
Sortie : coverage-ts-2/gen-results/<slot>/run-result.json
Idempotent : run-result existant = skip.
Run: uv run python scripts/act2/ts_v2_label_exec.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import argparse

AP = argparse.ArgumentParser()
AP.add_argument("--dir", required=True, help="répertoire campagne (coverage-ts-9-flash|pinned)")
ARGS, _ = AP.parse_known_args()
Q = ROOT / "data" / "landing" / "act2-pilot" / ARGS.dir
RESULTS = Q / "gen-results"
STAGING = Q / "staging-extract.json"
HOST = "Kimsufi-standard"

RUNNERS = {
    "omniroute": {"remote": "~/OmniRoute",
                  "cmd": "cd ~/OmniRoute && timeout 240 node --import tsx/esm --test --test-reporter=tap {spec} 2>&1",
                  "kind": "node"},
    "zod": {"remote": "~/zod-source",
            "cmd": "cd ~/zod-source && timeout 240 npx vitest run --no-cache --reporter=tap {spec} 2>&1",
            "kind": "vitest4"},
    "date-fns": {"remote": "~/date-fns-source",
                 "cmd": "cd ~/date-fns-source/pkgs/core && timeout 240 npx vitest run --no-cache --reporter=tap {spec} 2>&1",
                 "kind": "vitest8"},
}


def sh_local(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def sh_remote(cmd: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return sh_local(["ssh", "-o", "ConnectTimeout=12", HOST, cmd], timeout=timeout)


def _clean(name: str) -> str:
    return re.sub(r"^\d+ - ", "", name.split(" # ")[0]).strip()


def parse_leaf(line: str, kind: str) -> tuple[str, str] | None:
    if kind == "node":
        l = line.strip()
        if l.startswith("not ok "):
            return l[7:].split(" # ")[0].strip(), "failed"
        if l.startswith("ok "):
            return l[3:].split(" # ")[0].strip(), "passed"
        return None
    if kind == "vitest4":
        if not line.startswith("    ") or line.rstrip().endswith("{"):
            return None
        l = line.strip()
        if l.startswith("not ok "):
            return _clean(l[7:]), "failed"
        if l.startswith("ok "):
            return _clean(l[3:]), "passed"
        return None
    if kind == "vitest8":
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent < 8 or line.rstrip().endswith("{"):
            return None
        if stripped.startswith("not ok "):
            return _clean(stripped[7:]), "failed"
        if stripped.startswith("ok "):
            return _clean(stripped[3:]), "passed"
    return None


def node_test_remote(spec: str, repo: str) -> dict:
    """Runner par repo ; feuilles TAP parsées selon le format vitest/node."""
    runner = RUNNERS[repo]
    raw = sh_remote(runner["cmd"].format(spec=spec), timeout=320).stdout
    per_test = []
    for line in raw.splitlines():
        leaf = parse_leaf(line, runner["kind"])
        if leaf:
            per_test.append({"name": leaf[0], "status": leaf[1]})
    return {"rc": 0, "per_test": per_test, "tail": raw[-600:]}


def _check_clean(repo: str) -> str:
    return sh_remote(f"cd {RUNNERS[repo]['remote']} && git status --porcelain | head -1").stdout.strip()


def run_slot(slot_dir: Path, task: dict) -> dict:
    rec = json.loads((slot_dir / "rec.json").read_text())
    iid = rec["task"]
    repo = task.get("repo", "omniroute")
    remote = RUNNERS[repo]["remote"]
    out = {"task": iid, "slot": slot_dir.name, "campaign": ARGS.dir, "repo": repo,
           "window": "coverage-ts-v15", "author": rec.get("author"),
           "draw": rec.get("draw"), "diff_sha256": rec.get("diff_sha256"),
           "spec": task["spec"], "target": task["target"]}
    diff_f = slot_dir / "diff.patch"
    if not diff_f.is_file() or not diff_f.read_text().strip():
        return {**out, "error": "pas de diff.patch"}
    if _check_clean(repo):
        return {**out, "error": "worktree remote non propre avant slot"}

    buggy = Q / f"{iid.replace('/', '_')}.buggy.py"
    try:
        # 1) poser l'état infecté
        up = sh_local(["scp", "-q", str(buggy), f"{HOST}:{remote}/{task['target']}"], timeout=120)
        if up.returncode != 0:
            return {**out, "error": "scp buggy échoué"}
        import hashlib as _h
        local_sha = _h.sha256(buggy.read_bytes()).hexdigest()[:16]
        remote_sha = sh_remote(f"sha256sum {remote}/{task['target']} | cut -c1-16").stdout.strip()
        out["buggy_sha_check"] = {"local": local_sha, "remote": remote_sha, "match": local_sha == remote_sha}
        if local_sha != remote_sha:
            return {**out, "error": "POSE BUGGY NON VÉRIFIÉE par sha (écart scp/cache)"}
        vbug = node_test_remote(task["spec"], repo)
        failed_bug = [t["name"] for t in vbug["per_test"] if t["status"] == "failed"]
        f2p_set = set(task["f2p"])
        red = sorted(f2p_set & set(failed_bug))
        if not red:
            return {**out, "error": "contrôle positif échoué : F2P pas rouges sur l'état buggy",
                    "bug_tail": vbug["tail"]}
        out["bug_applied"] = True  # état infecté posé + contrôle positif rouge
        out["f2p_red_after_bug"] = red
        # 2) poser le diff candidat — git strict d'abord, puis patch -l --fuzz
        # (les diffs modèles hallucinent parfois le whitespace du contexte :
        #  git 2.51 skip silencieusement, patch -l l'applique — leçon coverage-ts-2)
        tmpd = slot_dir / ".remote.diff"
        tmpd.write_text(diff_f.read_text())
        upd = sh_local(["scp", "-q", str(tmpd), f"{HOST}:/tmp/genfam-cand.diff"], timeout=120)
        tmpd.unlink(missing_ok=True)
        if upd.returncode != 0:
            return {**out, "error": "scp diff échoué"}
        sha_pre = sh_remote(f"sha256sum {remote}/{task['target']} | cut -c1-64").stdout.strip()
        ap = sh_remote(f"cd {remote} && git apply --recount /tmp/genfam-cand.diff 2>&1")
        apply_mode = "strict-git" if ap.returncode == 0 else None
        sha_post = sh_remote(f"sha256sum {remote}/{task['target']} | cut -c1-64").stdout.strip()
        fallback_msg = ""
        if apply_mode is None or sha_pre == sha_post:
            ap2 = sh_remote(f"cd {remote} && patch -p1 -l --fuzz=3 -s < /tmp/genfam-cand.diff 2>&1")
            fallback_msg = ap2.stdout + ap2.stderr
            sha_post = sh_remote(f"sha256sum {remote}/{task['target']} | cut -c1-64").stdout.strip()
            if sha_pre != sha_post:
                apply_mode = "patch-whitespace-fuzz"
        applied = sha_pre != sha_post  # vérifié par contenu, jamais par HEAD (buggy pré-posé)
        out["patch_applied"] = applied
        out["apply_mode"] = apply_mode
        if not applied:
            return {**out, "apply_err": (ap.stdout + ap.stderr + fallback_msg)[-400:]}
        # 3) vitest complet du spec
        v = node_test_remote(task["spec"], repo)
        failed = [t["name"] for t in v["per_test"] if t["status"] == "failed"]
        passed = [t["name"] for t in v["per_test"] if t["status"] == "passed"]
        out["vitest_rc"] = v["rc"]
        # tails au FORMAT TEXTE (comme pytest) — jamais le JSON du reporter :
        # rules_v1 classifie du texte, un payload JSON la polluerait
        lines = [f"{'failed' if t['status'] == 'failed' else 'passed'}: {t['name']}"
                 for t in v["per_test"]]
        text_tail = "\n".join(lines) or v["tail"][-400:]
        f2p_still_red = sorted(f2p_set & set(failed))
        out["f2p_rc"] = 0 if (not f2p_still_red and v["rc"] == 0) else 1
        out["f2p_tail"] = text_tail
        p2p = [n for n in passed if n not in f2p_set]
        p2p_failed = [n for n in failed if n not in f2p_set]
        if p2p or p2p_failed:
            out["p2p_rc"] = 0 if not p2p_failed else 1
            out["p2p_tail"] = text_tail
        else:
            out["p2p_rc"] = None  # spec sans autres tests ⇒ pas de veto
        if v["rc"] != 0 and not failed:
            out["f2p_tail"] = v["tail"][-600:]  # SUITE-ERROR visible, pas deviné
        return out
    finally:
        sh_remote(f"cd {remote} && git checkout -- . && rm -f /tmp/genfam-cand.diff", timeout=120)
        if _check_clean(repo):
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
        print(f"{sd.name[:56]:56} bug={len(r.get('f2p_red_after_bug', []))} "
              f"patch={r.get('patch_applied')} f2p_rc={r.get('f2p_rc')} p2p_rc={r.get('p2p_rc')}"
              + (f" ERR={r.get('error')}" if r.get("error") else ""), flush=True)
    print(f"\n== TSv15-L : {done} déjà mesurés, {run} exécutés, {errors} erreurs ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
