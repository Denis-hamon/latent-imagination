#!/usr/bin/env python3
"""Story coverage-ts-v7 — labellisation stricte DISTANTE VITEST multi-sources
(zod + date-fns) sur Kimsufi-standard. Dérivé ts_v6_label_exec (même contrat
rules-v1 : bug_applied, f2p_rc/p2p_rc, tails TEXTE, restauration git) avec :
  - registry de runners vitest par repo (feuilles TAP : zod indent 4,
    date-fns indent >=8 sans accolade finale — describe/file-level exclus) ;
  - protection DW-35 : timeout 240 s par run vitest ; TimeoutExpired local OU
    timeout distant => quarantaine-timeout (jamais de hang, jamais de devinette).
Run: uv run python scripts/act2/ts_v7_label_exec.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "coverage-ts-7"
RESULTS = Q / "gen-results"
STAGING = Q / "staging-extract.json"
HOST = "Kimsufi-standard"

RUNNERS = {
    "zod": {"remote": "~/zod-source",
            "cmd": "cd ~/zod-source && timeout 240 npx vitest run --reporter=tap {spec} 2>&1",
            "leaf": (re.compile(r"^    (not ok|ok) \d+ - (.+?)(?: # time=.*)?$"),)},
    "date-fns": {"remote": "~/date-fns-source",
                 "cmd": "cd ~/date-fns-source/pkgs/core && timeout 240 npx vitest run --reporter=tap {spec} 2>&1",
                 "leaf": (re.compile(r"^(?: {8,})(not ok|ok) \d+ - (.+?)(?: # time=.*)?$"),)},
}


def sh_local(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def sh_remote(cmd: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return sh_local(["ssh", "-o", "ConnectTimeout=12", HOST, cmd], timeout=timeout)


def parse_leaf(line: str, rx: re.Pattern) -> tuple[str, str] | None:
    m = rx.match(line)
    if not m or line.rstrip().endswith("{"):
        return None
    name = m.group(2).split(" > ")[-1].strip()
    return name, "failed" if m.group(1) == "not ok" else "passed"


def vitest_remote(repo: str, spec: str) -> dict:
    r = RUNNERS[repo]
    raw = sh_remote(r["cmd"].format(spec=spec), timeout=300).stdout
    per_test = []
    for line in raw.splitlines():
        leaf = parse_leaf(line, r["leaf"][0])
        if leaf:
            per_test.append({"name": leaf[0], "status": leaf[1]})
    return {"rc": len(per_test), "per_test": per_test, "tail": raw[-600:]}


def _check_clean(remote: str) -> str:
    return sh_remote(f"cd {remote} && git status --porcelain | head -1").stdout.strip()


def run_slot(slot_dir: Path, task: dict) -> dict:
    rec = json.loads((slot_dir / "rec.json").read_text())
    iid = rec["task"]
    repo = task["repo"]
    remote = RUNNERS[repo]["remote"]
    out = {"task": iid, "slot": slot_dir.name, "campaign": "coverage-ts-7",
           "window": "coverage-ts-v7", "author": rec.get("author"),
           "draw": rec.get("draw"), "diff_sha256": rec.get("diff_sha256"),
           "repo": repo, "spec": task["spec"], "target": task["target"]}
    diff_f = slot_dir / "diff.patch"
    if not diff_f.is_file() or not diff_f.read_text().strip():
        return {**out, "error": "pas de diff.patch"}
    if _check_clean(remote):
        return {**out, "error": "worktree remote non propre avant slot"}

    buggy = Q / f"{iid.replace('/', '_')}.buggy.py"
    try:
        try:
            return _inner(slot_dir, task, out, buggy, remote)
        except subprocess.TimeoutExpired:
            out["y_hint"] = None
            out["error"] = "quarantaine-timeout : vitest > 240 s (hazard DW-35, variante possiblement boucle infinie)"
            return out
    finally:
        sh_remote(f"cd {remote} && git checkout -- . && rm -f /tmp/genfam-cand.diff", timeout=120)
        if _check_clean(remote):
            out.setdefault("cleanup_warning", "restauration remote à vérifier")


def _inner(slot_dir: Path, task: dict, out: dict, buggy: Path, remote: str) -> dict:
    repo = task["repo"]
    # 1) poser l'état infecté
    up = sh_local(["scp", "-q", str(buggy), f"{HOST}:{remote}/{task['target']}"], timeout=120)
    if up.returncode != 0:
        return {**out, "error": "scp buggy échoué"}
    vbug = vitest_remote(repo, task["spec"])
    failed_bug = [t["name"] for t in vbug["per_test"] if t["status"] == "failed"]
    f2p_set = set(task["f2p"])
    red = sorted(f2p_set & set(failed_bug))
    if not red:
        # noms exacts peuvent différer du parseur quota : tout échec bug = signal
        red = sorted(failed_bug)[:8] if failed_bug else []
    if not red:
        return {**out, "error": "contrôle positif échoué : aucun test rouge sur l'état buggy",
                "bug_tail": vbug["tail"]}
    out["bug_applied"] = True
    out["f2p_red_after_bug"] = red
    # 2) poser le diff candidat — git strict puis patch -l --fuzz (leçon v2),
    # pose vérifiée par SHA de contenu (jamais par rc ni HEAD)
    diff_f = slot_dir / "diff.patch"
    tmpd = slot_dir / ".remote.diff"
    tmpd.write_text(diff_f.read_text())
    upd = sh_local(["scp", "-q", str(tmpd), f"{HOST}:/tmp/genfam-cand.diff"], timeout=120)
    tmpd.unlink(missing_ok=True)
    if upd.returncode != 0:
        return {**out, "error": "scp diff échoué"}
    target = task["target"]
    sha_pre = sh_remote(f"sha256sum {remote}/{target} | cut -c1-64").stdout.strip()
    ap = sh_remote(f"cd {remote} && git apply --recount /tmp/genfam-cand.diff 2>&1")
    apply_mode = "strict-git" if ap.returncode == 0 else None
    sha_post = sh_remote(f"sha256sum {remote}/{target} | cut -c1-64").stdout.strip()
    fallback_msg = ""
    if apply_mode is None or sha_pre == sha_post:
        ap2 = sh_remote(f"cd {remote} && patch -p1 -l --fuzz=3 -s < /tmp/genfam-cand.diff 2>&1")
        fallback_msg = ap2.stdout + ap2.stderr
        sha_post = sh_remote(f"sha256sum {remote}/{target} | cut -c1-64").stdout.strip()
        if sha_pre != sha_post:
            apply_mode = "patch-whitespace-fuzz"
    applied = sha_pre != sha_post
    out["patch_applied"] = applied
    out["apply_mode"] = apply_mode
    if not applied:
        return {**out, "apply_err": (ap.stdout + ap.stderr + fallback_msg)[-400:]}
    # 3) vitest complet du spec (état patché)
    v = vitest_remote(repo, task["spec"])
    failed = [t["name"] for t in v["per_test"] if t["status"] == "failed"]
    passed = [t["name"] for t in v["per_test"] if t["status"] == "passed"]
    if not v["per_test"]:
        out["vitest_rc"] = None
        out["f2p_tail"] = v["tail"][-600:] or "EMPTY_OUTPUT timeout probable (DW-35)"
        return {**out, "error": "aucune feuille TAP lisible (timeout/infra ?), tail conservée"}
    out["vitest_rc"] = 0 if not failed else 1
    lines = [f"{'failed' if t['status'] == 'failed' else 'passed'}: {t['name']}"
             for t in v["per_test"]]
    text_tail = "\n".join(lines)
    f2p_still_red = sorted(f2p_set & set(failed)) or sorted(set(red) & set(failed))
    out["f2p_rc"] = 0 if not f2p_still_red else 1
    out["f2p_tail"] = text_tail
    p2p = [n for n in passed if n not in set(red)]
    p2p_failed = [n for n in failed if n not in set(red)]
    if p2p or p2p_failed:
        out["p2p_rc"] = 0 if not p2p_failed else 1
        out["p2p_tail"] = text_tail
    else:
        out["p2p_rc"] = None
    return out


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
              + (f" ERR={r.get('error')[:70]}" if r.get("error") else ""), flush=True)
    print(f"\n== TSv7-L : {done} déjà mesurés, {run} exécutés, {errors} erreurs ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
