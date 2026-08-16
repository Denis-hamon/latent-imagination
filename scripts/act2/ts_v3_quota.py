#!/usr/bin/env python3
"""Window coverage-ts-v3 — builder du quota BI-ÉTAGE sur worldmonitor.

Étage wm-easy : mutants mono/double-point (l'auteur les répare ⇒ classe
positive). Étage wm-hard : mutants TRIPLES coordonnés (l'auteur y échoue ⇒
classe négative) — classe validée par les sondes de difficulté (mono 2/2,
double 2/2, triple 0/1 réparés). Chaque candidate est VÉRIFIÉE zéro-appel
(node --test TAP sur Kimsufi-standard, worktree worldmonitor sérialisé,
restauration git) avant d'entrer au quota ; les invalides sont écartées et
journalisées (jamais de tâche inventée).

Source AGPL : analyse + labels internes seulement — aucun patch répliqué hors
du serveur, les contenus mutés restent locaux à la mesure.
Run: uv run python scripts/act2/ts_v3_quota.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "ts-v3"
HOST = "Kimsufi-standard"
REMOTE = "~/worldmonitor"

MUTANTS = [
    # ---- 511 rate-limiter (classes validées par sondes) ----
    {"task_id": "worldmonitor__511.capacity_off_by_one", "tier": "wm-easy",
     "file": "scripts/_511-rate-limit.mjs", "test": "tests/511-rate-limit.test.mjs",
     "replacements": [("if (stamps.length < capacity) {",
                       "if (stamps.length <= capacity) {")],
     "problem": "Le bucket par host laisse passer capacity+1 appels : le 11e "
                "appel (capacité 10) n'attend plus la fenêtre suivante."},
    {"task_id": "worldmonitor__511.triple_coordinated_defects", "tier": "wm-hard",
     "file": "scripts/_511-rate-limit.mjs", "test": "tests/511-rate-limit.test.mjs",
     "replacements": [
         ("capacity: override?.capacity ?? defaultCapacity,",
          "capacity: defaultCapacity ?? override?.capacity,"),
         ("stamps = stamps.filter((t) => t > windowStart);",
          "stamps = stamps.filter((t) => t >= windowStart);"),
         ("const waitMs = Math.max(1, stamps[0] + windowMs - nowMs);",
          "const waitMs = Math.max(1, stamps[0] + windowMs);")],
     "problem": "Trois défauts coordonnés : précédence d'override inversée, "
                "attente en temps absolu, frontière de fenêtre inclusive."},
    # ---- bet-baserate (probabilités Laplace, pur) ----
    {"task_id": "worldmonitor__baserate.branch_swap", "tier": "wm-easy",
     "file": "scripts/_bet-baserate.mjs", "test": "tests/bet-baserate.test.mjs",
     "replacements": [
         ("if (delta <= requiredDelta) crossed += 1; // requiredDelta is negative for a downward bet",
          "if (delta >= requiredDelta) crossed += 1; // requiredDelta is negative for a downward bet")],
     "problem": "Le comptage des franchissements pour un pari à la baisse "
                "utilise la comparaison montante : fréquence empirique inversée."},
    {"task_id": "worldmonitor__baserate.triple_coordinated", "tier": "wm-hard",
     "file": "scripts/_bet-baserate.mjs", "test": "tests/bet-baserate.test.mjs",
     "replacements": [
         ("if (delta <= requiredDelta) crossed += 1; // requiredDelta is negative for a downward bet",
          "if (delta >= requiredDelta) crossed += 1; // requiredDelta is negative for a downward bet"),
         ("const smoothed = (crossed + PRIOR_ALPHA) / (deltas.length + PRIOR_ALPHA + PRIOR_BETA);",
          "const smoothed = crossed / deltas.length;"),
         ("return { probability: 0.4, method: 'prior_directional', n: 0, crossed: 0 };",
          "return { probability: 0.5, method: 'prior_directional', n: 0, crossed: 0 };")],
     "problem": "Trois défauts coordonnés : comparaison de franchissement "
                "inversée pour les paris descendants, lissage de Laplace retiré, "
                "prior directionnel aminci remplacé par 0.5 neutre."},
    {"task_id": "worldmonitor__511.host_rates_values_swapped", "tier": "wm-easy",
     "file": "scripts/_511-rate-limit.mjs", "test": "tests/511-rate-limit.test.mjs",
     "replacements": [(
        "'api.open511.gov.bc.ca': Object.freeze({ capacity: 1, windowMs: 1_000 }),",
        "'api.open511.gov.bc.ca': Object.freeze({ capacity: 1_000, windowMs: 1 }),")],
     "problem": "Les valeurs du taux BC Open511 sont échangées : capacité 1000 "
                "par fenêtre de 1 ms au lieu de 1 appel par seconde."},
    {"task_id": "worldmonitor__baserate.clamp_inverted", "tier": "wm-easy",
     "file": "scripts/_bet-baserate.mjs", "test": "tests/bet-baserate.test.mjs",
     "replacements": [(
        "return Math.max(0, Math.min(1, value));",
        "return Math.min(0, Math.max(1, value));")],
     "problem": "Le clamp de probabilité est inversé : toutes les probabilités "
                "sortent à 0 au lieu d'être bornées entre 0 et 1."},
    # ---- bet-templates (génération de paris, dédup, extras) ----
    {"task_id": "worldmonitor__templates.decorate_guard_negated", "tier": "wm-easy",
     "file": "scripts/_bet-templates.mjs", "test": "tests/bet-templates.test.mjs",
     "replacements": [("if (template.decorate) {", "if (!template.decorate) {")],
     "problem": "La garde du décorateur de template est inversée : decorate est "
                "appelé seulement quand il est absent (TypeError avalé) et jamais "
                "quand il existe — les extras de calibration disparaissent."},
    {"task_id": "worldmonitor__templates.triple_coordinated", "tier": "wm-hard",
     "file": "scripts/_bet-templates.mjs", "test": "tests/bet-templates.test.mjs",
     "replacements": [
         ("if (seen.has(dedupeKey)) continue;",
          "if (!seen.has(dedupeKey)) continue;"),
         ("if (!metric) continue; // feed absent or metric not extractable → no bet",
          "if (metric) continue; // feed absent or metric not extractable → no bet"),
         ("question = template.buildQuestion({ ...ctx, spec });",
          "question = template.buildQuestion(ctx);")],
     "problem": "Trois défauts coordonnés : la garde de métrique est inversée "
                "(feeds valides sautés), la déduplication ne garde que les "
                "doublons, et le contexte passé au question-builder perd le spec."},
]


def sh_remote(cmd: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                          capture_output=True, text=True, check=False, timeout=timeout)


def sh_local(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def node_test(test: str) -> tuple[list[str], int, str]:
    r = sh_remote(f"cd {REMOTE} && node --test --test-reporter=tap {test} 2>&1", timeout=600)
    failed, passed = [], 0
    for line in r.stdout.splitlines():
        l = line.strip()
        if l.startswith("not ok "):
            failed.append(l[7:].split(" # ")[0].strip())
        elif l.startswith("ok "):
            passed += 1
    return failed, passed, r.stdout[-400:]


def validate(m: dict) -> dict:
    st = sh_remote(f"cd {REMOTE} && git status --porcelain | head -1")
    if st.stdout.strip():
        return {"task_id": m["task_id"], "rejected": "worktree non propre"}
    orig = sh_remote(f"cd {REMOTE} && cat {m['file']}").stdout
    bug = orig
    for old, new in m["replacements"]:
        if old not in bug:
            return {"task_id": m["task_id"], "rejected": f"texte introuvable: {old[:50]}"}
        bug = bug.replace(old, new, 1)
    tmp = Q / f".tmp-{abs(hash(m['task_id'])) % 10**10}.mjs"
    tmp.write_text(bug)
    up = sh_local(["scp", "-q", str(tmp), f"{HOST}:{REMOTE}/{m['file']}"], timeout=120)
    tmp.unlink(missing_ok=True)
    if up.returncode != 0:
        return {"task_id": m["task_id"], "rejected": "scp échoué"}
    failed, passed, tail = node_test(m["test"])
    sh_remote(f"cd {REMOTE} && git checkout -- {m['file']}")
    dirty = sh_remote(f"cd {REMOTE} && git status --porcelain | head -1")
    if dirty.stdout.strip():
        return {"task_id": m["task_id"], "rejected": "restauration a échoué"}
    if not failed:
        return {"task_id": m["task_id"], "rejected": "aucun test nommé ne casse",
                "raw_tail": tail}
    return {"task_id": m["task_id"], "ok": True, "buggy": bug,
            "f2p": sorted(set(failed)), "p2p_n": passed,
            "file": m["file"], "test": m["test"], "problem": m["problem"],
            "tier": m["tier"]}


def main() -> int:
    Q.mkdir(parents=True, exist_ok=True)
    tasks, discarded = [], []
    for m in MUTANTS:
        print(f"validation {m['tier']:7} {m['task_id']} …", flush=True)
        r = validate(m)
        if r.pop("ok", False):
            buggy_f = Q / f"{r['task_id'].replace('/', '_')}.buggy.py"
            buggy_f.write_text(r.pop("buggy"))
            tasks.append({
                "instance_id": r["task_id"], "repo": "worldmonitor",
                "lang": "javascript", "test_runner": "node:test",
                "tier": r["tier"], "target": r["file"], "spec": r["test"],
                "patch": "", "gold": "",
                "buggy_sha256": sha256(buggy_f.read_bytes()).hexdigest(),
                "f2p": r["f2p"], "p2p_n": r["p2p_n"], "problem": r["problem"],
                "campaign": "coverage-ts-3", "window": "coverage-ts-v3"})
            print(f"  OK : {len(r['f2p'])} F2P, {r['p2p_n']} passés")
        else:
            discarded.append({**r, "discarded_at":
                              datetime.now(UTC).isoformat().replace("+00:00", "Z")})
            print(f"  ÉCARTÉ : {r.get('rejected')}")
    mani = {"window": "coverage-ts-v3", "envelope_calls_cap": 110,
            "probe_calls_already_consumed": 4,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "n_tasks": len(tasks),
            "tiers": {"wm-easy": sum(1 for t in tasks if t["tier"] == "wm-easy"),
                      "wm-hard": sum(1 for t in tasks if t["tier"] == "wm-hard")},
            "tasks": tasks}
    (Q / "quota-tasks.json").write_text(json.dumps(mani, indent=1) + "\n")
    with (Q / "discarded.jsonl").open("w") as fh:
        for d in discarded:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"\nquota : {len(tasks)} validées / {len(MUTANTS)} candidates "
          f"({len(discarded)} écartées)")
    if len(tasks) < 12:
        print(f"SHORTFALL vs cible 12 : {12 - len(tasks)} — disclosure à l'exécution")
    return 0


if __name__ == "__main__":
    sys.exit(main())
