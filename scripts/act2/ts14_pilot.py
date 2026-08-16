#!/usr/bin/env python3
"""Story 14.1 — PILOTE source de tâches TS juge-free (protocole swe-smith
répliqué pour vitest).

Sur un repo TS à tests réels (acre, licence "ours") :
  1. bug-patch = mutation typée (swap ours/theirs dans applyResolutions —
     l'équivalent TS des mutations opérateur swe-smith) ;
  2. application du bug → les tests vitest QUI DOIVENT ÉCHOUER sont identifiés
     (F2P) et ceux qui restent verts (P2P) — signal exécutable, zéro juge ;
  3. gold-patch = restauration → contrôle positif : la suite redevient verte ;
  4. le repo est remis dans son état d'origine (rien ne reste muté).

Sortie : data/landing/act2-pilot/ts14-pilot/pilot-task.json — la première
tâche TS {instance_id, repo, bug_patch, gold_patch, f2p, p2p, problem},
même forme que les tâches smith. Si l'une des trois étapes échoue, le pilote
REFUSE et divulgue (jamais de signal supposé).

Run: uv run python scripts/act2/ts14_pilot.py [--repo <chemin worktree acre>]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "landing" / "act2-pilot" / "ts14-pilot"
DEFAULT_REPO = Path.home() / "Acre" / "worktrees" / "wt-20-13"
TARGET = "packages/blocks/src/merge/diff3-merge.ts"
TESTFILE = "src/merge/__tests__/diff3-merge.test.ts"

# Mutation : swap des sorties ours/theirs — sémantique pure, structure
# identique (contexte unique, pas de casse syntaxique ; équivalent TS des
# mutations opérateur swe-smith)
BUG_APPLY = [
    ('    if (resolution.choice === "ours") {\n      out.push(...segment.oursLines);',
     '    if (resolution.choice === "ours") {\n      out.push(...segment.theirsLines);'),
    ('    } else if (resolution.choice === "theirs") {\n      out.push(...segment.theirsLines);',
     '    } else if (resolution.choice === "theirs") {\n      out.push(...segment.oursLines);'),
]


def sh(cmd: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          check=False, timeout=timeout)


def vitest(repo: Path) -> tuple[bool, list[str], list[str], str]:
    """Retourne (all_green, tests_failed, tests_passed, raw_tail)."""
    r = sh(["node_modules/.bin/vitest", "run", TESTFILE, "--reporter=json"],
           cwd=repo / "packages/blocks", timeout=600)
    raw = r.stdout + r.stderr
    failed, passed = [], []
    try:
        start = raw.find("{")
        data = json.loads(raw[start:raw.rfind("}") + 1])
        for tr in data.get("testResults", []):
            for ar in tr.get("assertionResults", []):
                name = " > ".join(ar.get("ancestorTitles", [])) + " > " + ar.get("title", "")
                (failed if ar.get("status") == "failed" else passed).append(name)
    except (json.JSONDecodeError, ValueError):
        pass
    if r.returncode != 0 and not failed:
        # suite-level error (compile/transform) : signal honnête, distinct de
        # l'absence de signal — rapporté comme tel, jamais deviné comme un pass
        failed = ["<SUITE-ERROR: vitest a échoué sans assertion nominale>"]
    return len(failed) == 0, failed, passed, raw[-800:]


def make_bug_patch(repo: Path) -> str | None:
    p = repo / TARGET
    orig = p.read_text()
    bug = orig
    for old, new in BUG_APPLY:
        if old not in bug:
            return None
        bug = bug.replace(old, new, 1)
    if bug == orig:
        return None
    p.write_text(bug)
    r = sh(["git", "diff", "--", TARGET], cwd=repo)
    patch = r.stdout
    p.write_text(orig)  # le patch est capturé, l'arbre redevient propre
    return patch if patch.strip() else None


def apply_patch(repo: Path, patch: str, reverse: bool = False) -> bool:
    cmd = ["git", "apply"] + (["-R"] if reverse else []) + ["-"]
    r = subprocess.run(cmd, cwd=repo, input=patch, capture_output=True, text=True, check=False)
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(DEFAULT_REPO))
    args = ap.parse_args()
    repo = Path(args.repo)
    if not (repo / TARGET).is_file():
        print(f"ABSENT: {repo / TARGET}")
        return 2
    clean = sh(["git", "status", "--porcelain"], cwd=repo).stdout.strip()
    if clean:
        print(f"ABORT: worktree non propre (pré-condition) :\n{clean[:300]}")
        return 2

    print("1/ baseline verte exigée…", flush=True)
    green0, _, n_pass0, _raw0 = vitest(repo)
    if not green0:
        print("ABORT: la baseline n'est pas verte — pas de pilote sur base cassée")
        return 3

    print("2/ construction du bug-patch (mutation ours/theirs)…", flush=True)
    bug_patch = make_bug_patch(repo)
    if not bug_patch:
        print("ABORT: mutation non applicable à ce fichier")
        return 3
    if not apply_patch(repo, bug_patch):
        print("ABORT: git apply du bug-patch a échoué")
        return 3
    try:
        print("3/ le bug doit CASSER des tests nommés (F2P)…", flush=True)
        green_bug, failed, passed, raw_bug = vitest(repo)
        if green_bug or not failed:
            print("REFUS: le bug ne casse aucun test — signal invalide, pas de tâche")
            return 3
        f2p = sorted(failed)
        p2p = sorted(passed)
        print(f"   F2P ({len(f2p)}) : {f2p[0]} …")
        print(f"   P2P ({len(p2p)}) restent verts")
        if not apply_patch(repo, bug_patch, reverse=True):
            print("ABORT: restauration du gold impossible")
            return 3
        print("4/ contrôle positif : le gold (restauration) reverdit tout…", flush=True)
        green_gold, failed_gold, _, _ = vitest(repo)
        if not green_gold:
            print(f"REFUS: la restauration ne reverdit pas ({len(failed_gold)} échecs)")
            return 3
    finally:
        # état final : arbre propre, quoi qu'il arrive
        if sh(["git", "status", "--porcelain"], cwd=repo).stdout.strip():
            apply_patch(repo, bug_patch, reverse=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    task = {
        "instance_id": "acre__blocks.diff3-merge.apply_resolutions_swap",
        "repo": "acre/packages/blocks",
        "lang": "typescript", "test_runner": "vitest",
        "target": TARGET,
        "patch": bug_patch,
        "gold": bug_patch,  # la restauration du bug = le gold (symétrie swe-smith)
        "f2p": f2p, "p2p": p2p,
        "problem": ("applyResolutions inverse les choix ours/theirs : la "
                    "résolution d'un conflit de fusion 3-way rend le texte du "
                    "mauvais côté. F2P : les tests de résolution."),
        "provenance": {"campaign": "ts14-pilot", "window": "coverage-nextjs-ts",
                       "rights": "own repo (licence ours)", "created_at":
                       datetime.now(UTC).isoformat().replace("+00:00", "Z")},
    }
    out = OUT_DIR / "pilot-task.json"
    out.write_text(json.dumps(task, indent=1, ensure_ascii=False) + "\n")
    report = {"baseline_green": True, "n_pass_baseline": len(n_pass0),
              "bug_cassait": len(f2p), "p2p_restes": len(p2p),
              "gold_reverdit": True,
              "signal": "F2P/P2P prouvé bout-en-bout sur vitest, zéro juge",
              "arbre_final": "propre (vérifié git status)",
              "f2p": f2p, "p2p_sample": p2p[:6],
              "vitest_tail_bug": raw_bug[-400:]}
    (OUT_DIR / "pilot-report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"\nPILOTE OK : {len(f2p)} F2P, {len(p2p)} P2P, gold reverdit ✓ → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
