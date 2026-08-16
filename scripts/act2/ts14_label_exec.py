#!/usr/bin/env python3
"""Story 14.3 — labellisation stricte TS (vitest, worktree acre SÉRIALISÉ).

Chaîne identique en discipline à genfam_label_exec (docker), adaptée au
TS window (amendement enregistré : la gate de compilation/validité est celle
du langage — vitest/TS — pas py_compile) :
  worktree propre exigé → apply bug-patch → contrôle positif : les F2P DOIVENT
  échouer → apply diff candidat (git apply strict) → vitest sur le fichier de
  test du module → F2P (nommés) + P2P → restauration de l'arbre (finally).

Zéro juge : le label vient du runner vitest, les raw tails sont la preuve
(FR-3). Sortie : coverage-ts-1/gen-results/<slot>/run-result.json.
Idempotent (run-result existant = skip).
Run: uv run python scripts/act2/ts14_label_exec.py [--repo <worktree>]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "coverage-ts-1"
RESULTS = Q / "gen-results"
STAGING = Q / "staging-extract.json"
PKG = "packages/blocks"
DEFAULT_REPO = Path.home() / "Acre" / "worktrees" / "wt-20-13"


def sh(cmd: list[str], cwd: Path, timeout: int = 900, data: str | None = None):
    return subprocess.run(cmd, cwd=cwd, input=data, capture_output=True,
                          text=True, check=False, timeout=timeout)


def vitest_json(repo: Path, test: str) -> dict:
    r = sh(["node_modules/.bin/vitest", "run", test, "--reporter=json"],
           cwd=repo / PKG, timeout=900)
    raw = r.stdout + r.stderr
    try:
        start = raw.find("{")
        return {"rc": r.returncode, "data": json.loads(raw[start:raw.rfind("}") + 1]),
                "raw": raw}
    except (json.JSONDecodeError, ValueError):
        return {"rc": r.returncode, "data": None, "raw": raw}


def run_slot(slot_dir: Path, task: dict, repo: Path) -> dict:
    rec = json.loads((slot_dir / "rec.json").read_text())
    iid = rec["task"]
    out = {"task": iid, "slot": slot_dir.name, "campaign": "coverage-ts-1",
           "window": "coverage-ts-v1", "author": rec.get("author"),
           "draw": rec.get("draw"), "diff_sha256": rec.get("diff_sha256"),
           "test": task["test"], "target": task["target"]}
    diff = slot_dir / "diff.patch"
    if not diff.is_file() or not diff.read_text().strip():
        return {**out, "error": "pas de diff.patch"}

    dirty = sh(["git", "status", "--porcelain"], cwd=repo).stdout.strip()
    if dirty:
        return {**out, "error": f"worktree non propre avant slot: {dirty[:200]}"}
    try:
        bg = sh(["git", "apply", "-"], cwd=repo, data=task["patch"])
        out["bug_applied"] = bg.returncode == 0
        if not out["bug_applied"]:
            return {**out, "bug_apply_err": bg.stderr[-300:]}
        vbug = vitest_json(repo, task["test"])
        f2p_bug_failed = _failed_names(vbug)
        out["f2p_red_after_bug"] = sorted(set(f2p_bug_failed) & set(task["f2p"]))
        if not out["f2p_red_after_bug"]:
            # le bug ne recasse pas les F2P attendus : chaîne invalide, quarantine
            return {**out, "error": "contrôle positif échoué : F2P pas rouges après bug"}
        ap = sh(["git", "apply", "-"], cwd=repo, data=diff.read_text())
        out["patch_applied"] = ap.returncode == 0
        if not out["patch_applied"]:
            return {**out, "apply_err": ap.stderr[-400:]}
        v = vitest_json(repo, task["test"])
        failed = _failed_names(v)
        out["vitest_rc"] = v["rc"]
        out["f2p_tail"] = _tail_for(v, task["f2p"])
        out["f2p_rc"] = 0 if not (set(task["f2p"]) & set(failed)) and v["rc"] == 0 else 1
        if out["f2p_rc"] == 0 and task.get("p2p"):
            out["p2p_rc"] = 0 if not (set(task["p2p"]) & set(failed)) else 1
            out["p2p_tail"] = _tail_for(v, task["p2p"])
        elif out["f2p_rc"] == 0:
            out["p2p_rc"] = None  # non déclarés ⇒ pas de veto
        if v["rc"] != 0 and not failed:
            out["f2p_tail"] = v["raw"][-800:]  # SUITE-ERROR visible, pas deviné
        return out
    finally:
        cleanup = sh(["git", "checkout", "--", "."], cwd=repo, timeout=120)
        if cleanup.returncode != 0 or sh(["git", "status", "--porcelain"], cwd=repo).stdout.strip():
            out.setdefault("cleanup_warning", "restauration worktree à vérifier")


def _failed_names(v: dict) -> list[str]:
    failed = []
    if not v["data"]:
        return failed
    for tr in v["data"].get("testResults", []):
        for ar in tr.get("assertionResults", []):
            if ar.get("status") == "failed":
                failed.append(" > ".join(ar.get("ancestorTitles", []))
                              + " > " + ar.get("title", ""))
    return failed


def _tail_for(v: dict, names: list[str]) -> str:
    if not v["data"]:
        return v["raw"][-600:]
    parts = []
    for tr in v["data"].get("testResults", []):
        for ar in tr.get("assertionResults", []):
            full = " > ".join(ar.get("ancestorTitles", [])) + " > " + ar.get("title", "")
            if full in names:
                msgs = " | ".join((m.get("message") or "")[:200]
                                  for m in ar.get("failureMessages", []) or [])
                parts.append(f"{ar.get('status')}: {full} {msgs}".strip())
    return "\n".join(parts)[-800:] or v["raw"][-400:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(DEFAULT_REPO))
    args = ap.parse_args()
    repo = Path(args.repo)
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
        rec = json.loads((sd / "rec.json").read_text())
        task = by_iid.get(rec["task"])
        if task is None:
            errors += 1
            continue
        r = run_slot(sd, task, repo)
        (sd / "run-result.json").write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
        run += 1
        errors += 1 if r.get("error") else 0
        print(f"{sd.name[:58]:58} bug={r.get('bug_applied')} patch={r.get('patch_applied')} "
              f"f2p_rc={r.get('f2p_rc')} p2p_rc={r.get('p2p_rc')}"
              + (f" ERR={r.get('error')}" if r.get("error") else ""), flush=True)
    print(f"\n== TS-L : {done} déjà mesurés, {run} exécutés, {errors} erreurs ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
