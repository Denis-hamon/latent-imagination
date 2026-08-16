#!/usr/bin/env python3
"""Window coverage-ts-v3 (préparation) — DIFFICULTY-PROBE sur worldmonitor
(source public-worldmonitor-ts, AGPL analyse-interne seulement).

Tests NODE:NATIFS (node --test, .mjs — 769 fichiers du corpus sans npm
install) : logique applicative réelle À ÉTAT (rate-limiter token bucket
per-host, pacing), la classe de difficulté qui manquait (les mutants
mono-fonction kimsufi/acre étaient réparés à 94 %).

Étape 1 (--stage verify, zéro appel) : mutation → node --test → F2P NOMMÉS
(lignes "not ok" du TAP) → restauration (git checkout) → vert.
Étape 2 (--stage author, appels comptés à l'enveloppe v3) : 2 générations de
l'auteur épinglé (T=0.7, classe prompt pilot_run gelée, lane strict puis
patch -l --fuzz comme en v2 — leçon whitespace).

Règle fenêtre v2 réutilisée : ≥1 échec auteur sur 2 ⇒ classe validée ;
2/2 réparés ⇒ escalade déclarée.
Run: uv run python scripts/act2/ts_v3_probe.py --stage verify|author
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "coverage-ts-3"
HOST = "Kimsufi-standard"
REMOTE = "~/worldmonitor"

MUTANTS = [
    # ESCALADE 2/2 (dernière permise par la règle fenêtre v2) : mutant TRIPLE
    # coordonné — les trois défauts doivent être réparés ENSEMBLE pour
    # reverdir la suite (précédence override + attente absolue + frontière).
    # Un test par fichier ne reverdit que si les trois sont corrigés.
    {
        "task_id": "worldmonitor__511.triple_coordinated_defects",
        "file": "scripts/_511-rate-limit.mjs",
        "test": "tests/511-rate-limit.test.mjs",
        "replacements": [
            ("capacity: override?.capacity ?? defaultCapacity,",
             "capacity: defaultCapacity ?? override?.capacity,"),
            ("stamps = stamps.filter((t) => t > windowStart);",
             "stamps = stamps.filter((t) => t >= windowStart);"),
            ("const waitMs = Math.max(1, stamps[0] + windowMs - nowMs);",
             "const waitMs = Math.max(1, stamps[0] + windowMs);"),
        ],
        "problem": "Trois défauts coordonnés dans le rate-limiter 511 : la "
                   "précédence des overrides par host est inversée (l'override "
                   "est ignoré), le calcul d'attente est en temps absolu au lieu "
                   "d'être relatif à maintenant, et la purge du bucket conserve "
                   "les timestamps situés exactement sur la frontière de fenêtre.",
    },
]


def sh_remote(cmd: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                          capture_output=True, text=True, check=False, timeout=timeout)


def node_test(test: str) -> tuple[list[str], int, str]:
    """Retourne (tests échoués nommés, n_passed, tail) via le TAP de node --test."""
    r = sh_remote(f"cd {REMOTE} && node --test --test-reporter=tap {test} 2>&1", timeout=600)
    failed, passed = [], 0
    for line in r.stdout.splitlines():
        l = line.strip()  # TAP node --test : sous-tests indentés
        if l.startswith("not ok "):
            failed.append(l[7:].split(" # ")[0].strip())
        elif l.startswith("ok "):
            passed += 1
    return failed, passed, r.stdout[-500:]


def verify_stage() -> int:
    Q.mkdir(parents=True, exist_ok=True)
    results = []
    for m in MUTANTS:
        print(f"chaîne {m['task_id']} …", flush=True)
        st = sh_remote(f"cd {REMOTE} && git status --porcelain | head -1")
        if st.stdout.strip():
            print("  ABORT: worktree worldmonitor non propre")
            return 2
        orig = sh_remote(f"cd {REMOTE} && cat {m['file']}").stdout
        bug = orig
        for old, new in m["replacements"]:
            if old not in bug:
                print(f"  ABORT: texte mutant introuvable ({old[:40]}…)")
                return 3
            bug = bug.replace(old, new, 1)
        tmp = Q / f".tmp-{m['task_id'][-12:]}.mjs"
        tmp.write_text(bug)
        subprocess.run(["scp", "-q", str(tmp), f"{HOST}:{REMOTE}/{m['file']}"],
                       capture_output=True, check=False, timeout=120)
        tmp.unlink(missing_ok=True)
        failed, passed, tail = node_test(m["test"])
        sh_remote(f"cd {REMOTE} && git checkout -- {m['file']}")
        if not failed:
            print(f"  RÉFUSÉ : aucun test nommé ne casse — pas de signal ({tail[:80]})")
            results.append({"task_id": m["task_id"], "rejected": "aucun F2P"})
            continue
        (Q / f"{m['task_id'].replace('/', '_')}.buggy.py").write_text(bug)
        results.append({"task_id": m["task_id"], "f2p": failed, "p2p_n": passed,
                        "file": m["file"], "test": m["test"], "problem": m["problem"],
                        "buggy_sha256": sha256(bug.encode()).hexdigest()})
        print(f"  OK : {len(failed)} F2P ({failed[0][:60]}…), {passed} passés")
    valid = [r for r in results if "rejected" not in r]
    (Q / "probe-manifest.json").write_text(json.dumps(
        {"window": "coverage-ts-v3", "stage": "verify", "mutants": results,
         "at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}, indent=1) + "\n")
    print(f"vérification : {len(valid)}/{len(MUTANTS)} mutants avec signal F2P")
    return 0 if valid else 3


def author_stage() -> int:
    mani = json.loads((Q / "probe-manifest.json").read_text())
    valid = [m for m in mani["mutants"] if "rejected" not in m]
    spec = importlib.util.spec_from_file_location("gg", ROOT / "scripts" / "act2" / "genfam_gen.py")
    gg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gg)
    spec2 = importlib.util.spec_from_file_location("pr2", ROOT / "scripts" / "act2" / "pilot_run.py")
    pr = importlib.util.module_from_spec(spec2)
    sys.modules["pilot_run"] = pr
    spec2.loader.exec_module(pr)
    pr.call_model = gg.call_t07
    os.environ["PILOT_CAMPAIGN_DIR"] = "coverage-ts-3"
    pr.os.environ["PILOT_CAMPAIGN_DIR"] = "coverage-ts-3"
    log = Q / "call-log.jsonl"
    rows = []
    for m in valid:
        task = {"instance_id": m["task_id"], "problem": m["problem"],
                "f2p": m["f2p"][:6], "target": m["file"]}
        try:
            g = pr.gen_patch(task)
            err = None
        except Exception as e:  # noqa: BLE001 — erreur endpoint auditée
            g, err = None, str(e)[:300]
        row = {"ts": datetime.now(UTC).isoformat(), "window": "coverage-ts-v3",
               "stage": "difficulty-probe", "slot": m["task_id"],
               "model": gg.MODEL, "campaign": "coverage-ts-3", "temperature": 0.7}
        if err:
            row["error"] = err
        else:
            row.update({"prompt_sha256": g["prompt_sha256"],
                        "reply_sha256": g["reply_sha256"], "raw_reply": g["raw_reply"],
                        "usage": g["usage"]})
            buggy = (Q / f"{m['task_id'].replace('/', '_')}.buggy.py").read_text()
            san = pr.extract_diff_sanitized(g["raw_reply"])
            diff = mode = None
            if san:
                diff, _e = pr.apply_and_export_debug(buggy, san + "\n", m["file"])
                mode = "strict-git" if diff else None
                if diff is None:
                    diff, _e2 = gg.apply_fuzz_reexport(buggy, san + "\n", m["file"])
                    mode = "fuzz-reexport" if diff else None
            row.update({"diff_mode": mode,
                        "diff_sha256": sha256(diff.encode()).hexdigest() if diff else None})
            if diff:
                (Q / f"{m['task_id'].replace('/', '_')}-probe.diff").write_text(diff)
        with log.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        rows.append(row)
        print(f"{m['task_id']}: " +
              (f"diff produit ({row.get('diff_mode')})" if row.get("diff_sha256")
               else f"PAS DE DIFF {'(err: ' + row['error'][:50] + ')' if 'error' in row else '(no-diff)'}"))
    n_diff = sum(1 for r in rows if r.get("diff_sha256"))
    verdict = ("CLASSE VALIDÉE (≥1 échec) — gel possible sur cette classe"
               if n_diff < len(rows) else
               "2/2 réparés — ESCALADE de difficulté requise (règle fenêtre v2)")
    (Q / "probe-verdict.json").write_text(json.dumps(
        {"window": "coverage-ts-v3", "n_mutants": len(rows),
         "n_author_repaired": n_diff, "verdict": verdict,
         "at": datetime.now(UTC).isoformat()}, indent=1) + "\n")
    print(f"\nSONDE AUTEUR : {n_diff}/{len(rows)} réparés → {verdict}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("verify", "author"), required=True)
    a = ap.parse_args()
    sys.exit(verify_stage() if a.stage == "verify" else author_stage())
