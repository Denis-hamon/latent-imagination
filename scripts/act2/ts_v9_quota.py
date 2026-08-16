#!/usr/bin/env python3
"""Window coverage-ts-v9 — quota TRIPLES HARD (héritage v4) sur OmniRoute (MIT), validés zéro-appel.

Étage wm-easy : mutants mono/double-point (l'auteur les répare ⇒ classe
positive). Étage wm-hard : mutants TRIPLES coordonnés (l'auteur y échoue ⇒
classe négative) — classe validée par les sondes de difficulté (mono 2/2,
double 2/2, triple 0/1 réparés). Chaque candidate est VÉRIFIÉE zéro-appel
(node --test TAP sur Kimsufi-standard, worktree worldmonitor sérialisé,
restauration git) avant d'entrer au quota ; les invalides sont écartées et
journalisées (jamais de tâche inventée).

Source AGPL : analyse + labels internes seulement — aucun patch répliqué hors
du serveur, les contenus mutés restent locaux à la mesure.
Run: uv run python scripts/act2/ts_v9_quota.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "ts-v9"
HOST = "Kimsufi-standard"
REMOTE = "~/OmniRoute"

MUTANTS = [
    # ---- classe ts9-triple : 5 triples hard hérités de v4 (jamais générés
    # avec source-en-prompt ; strings vérifiés présents 1x dans le commit épinglé) ----
    {"task_id": "omniroute__lite.triple_coordinated", "tier": "ts9-triple",
     "file": "open-sse/services/compression/lite.ts", "test": "tests/unit/8169-lite-word-boundary-truncation.test.ts",
     "replacements": [
         ("const onWordBoundary = !isWordChar(content[cutIndex - 1]) || !isWordChar(content[cutIndex]);",
          "const onWordBoundary = isWordChar(content[cutIndex - 1]) && isWordChar(content[cutIndex]);"),
         ("if (msg.role !== \"tool\" || typeof msg.content !== \"string\") return msg;",
          "if (msg.role !== \"assistant\" || typeof msg.content !== \"string\") return msg;"),
         ("const MAX_TOOL_LENGTH = 2000;", "const MAX_TOOL_LENGTH = 20000;")],
     "problem": "La compression lite est cassée de trois façons à la fois : elle ne "
                "cible plus les messages outils, le seuil de troncature est décuplé, "
                "et quand une troncature a lieu elle coupe en plein mot."},
    {"task_id": "omniroute__combo.triple_gate", "tier": "ts9-triple",
     "file": "open-sse/services/combo/comboPredicates.ts", "test": "tests/unit/8376-econnrefused-breaker.test.ts",
     "replacements": [
         ("if (status !== 503) return false;", "if (status !== 502) return false;"),
         ("breakerHeader.toLowerCase() === \"open\") return true;",
          "breakerHeader.toLowerCase() === \"closed\") return true;"),
         ("return ALL_ACCOUNTS_RATE_LIMITED_PATTERNS.some((p) => p.test(errorText));",
          "return ALL_ACCOUNTS_RATE_LIMITED_PATTERNS.every((p) => p.test(errorText));")],
     "problem": "Trois défauts coordonnés dans la détection d'épuisement des "
                "comptes : la porte de statut ne reconnaît plus les 503, l'en-tête "
                "de circuit-breaker est inversé, et il faut que TOUS les motifs de "
                "message matchent au lieu d'un seul."},
    {"task_id": "omniroute__combo.triple_skiporder", "tier": "ts9-triple",
     "file": "open-sse/services/combo/comboPredicates.ts", "test": "tests/unit/8376-econnrefused-breaker.test.ts",
     "replacements": [
         ("if (provider && connectionId) {", "if (provider || connectionId) {"),
         ("exhaustedConnections.has(`${provider}:${connectionId}`)",
          "exhaustedConnections.has(`${connectionId}:${provider}`)"),
         ("if (provider && exhaustedProviders.has(provider)) {",
          "if (provider && !exhaustedProviders.has(provider)) {")],
     "problem": "Le ciblage des connexions épuisées dans le combo est triplement "
                "cassé : la garde exige provider OU connectionId au lieu des deux, "
                "la clé de dedup est construite dans le mauvais ordre, et les "
                "providers marqués épuisés sont traités comme sains (et inversement)."},
    {"task_id": "omniroute__affinity.triple_coordinated", "tier": "ts9-triple",
     "file": "open-sse/services/combo/promptCacheAffinity.ts", "test": "tests/unit/8370-priority-affinity-reorder.test.ts",
     "replacements": [
         ("if (score > winnerScore || (score === winnerScore && identity < winnerIdentity)) {",
          "if (score >= winnerScore) {"),
         ("return [identity, identity === winnerIdentity ? 1 : 0];",
          "return [identity, identity === winnerIdentity ? 0 : 1];"),
         ("strategy === \"priority\" ||", "strategy === \"priorities\" ||")],
     "problem": "Trois défauts coordonnés dans l'affinité prompt-cache : la "
                "sélection du gagnant écrase le départage à égalité, le score "
                "binaire retourné est inversé (le gagnant marque 0), et la "
                "stratégie priority n'est plus protégée."},
    {"task_id": "omniroute__usage.triple_coordinated", "tier": "ts9-triple",
     "file": "open-sse/utils/usageTracking.ts", "test": "tests/unit/8331-usage-buffer-inflation.test.ts",
     "replacements": [
         ("result.context_budget_input_tokens = result.input_tokens + buffer;",
          "result.input_tokens = result.input_tokens + buffer;"),
         ("result.context_budget_prompt_tokens = result.prompt_tokens + buffer;",
          "result.prompt_tokens = result.prompt_tokens + buffer;"),
         (".estimated === true) {", ".estimated !== true) {")],
     "problem": "Le suivi d'usage est triplement cassé : le buffer de sécurité est "
                "injecté dans les champs client input_tokens et prompt_tokens au "
                "lieu des seuls champs context_budget, et les usages heuristiques "
                "estimés reçoivent le buffer au lieu d'en être exemptés."},
]


def sh_remote(cmd: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                          capture_output=True, text=True, check=False, timeout=timeout)


def sh_local(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def node_test(test: str) -> tuple[list[str], int, str]:
    r = sh_remote(f"cd {REMOTE} && node --import tsx/esm --test --test-reporter=tap {test} 2>&1", timeout=600)
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
                "lang": "typescript", "test_runner": "node:test+tsx",
                "tier": r["tier"], "target": r["file"], "spec": r["test"],
                "patch": "", "gold": "",
                "buggy_sha256": sha256(buggy_f.read_bytes()).hexdigest(),
                "f2p": r["f2p"], "p2p_n": r["p2p_n"], "problem": r["problem"],
                "campaign": "coverage-ts-9", "window": "coverage-ts-v9"})
            print(f"  OK : {len(r['f2p'])} F2P, {r['p2p_n']} passés")
        else:
            discarded.append({**r, "discarded_at":
                              datetime.now(UTC).isoformat().replace("+00:00", "Z")})
            print(f"  ÉCARTÉ : {r.get('rejected')}")
    mani = {"window": "coverage-ts-v9", "envelope_calls_cap": 55,
            "probe_calls_already_consumed": 0,  # mis à jour après sonde
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "n_tasks": len(tasks),
            "tiers": {"ts9-triple": sum(1 for t in tasks if t["tier"] == "ts9-triple")},
            "tasks": tasks}
    (Q / "quota-tasks.json").write_text(json.dumps(mani, indent=1) + "\n")
    with (Q / "discarded.jsonl").open("w") as fh:
        for d in discarded:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"\nquota : {len(tasks)} validées / {len(MUTANTS)} candidates "
          f"({len(discarded)} écartées)")
    if len(tasks) < 5:
        print(f"SHORTFALL vs cible 5 : {5 - len(tasks)} — disclosure à l'exécution")
    return 0


if __name__ == "__main__":
    sys.exit(main())
