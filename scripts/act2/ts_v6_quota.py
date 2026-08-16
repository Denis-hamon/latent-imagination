#!/usr/bin/env python3
"""Window coverage-ts-v6 (négatifs-first) — builder du quota : candidats vérifiés zéro-appel sur OmniRoute (MIT),
fichiers neufs toolResultCompressor/hardBudget/strategySelector + ancres easy sur fichiers éprouvés.

Étage wm-easy : mutants mono/double-point (l'auteur les répare ⇒ classe
positive). Étage wm-hard : mutants TRIPLES coordonnés (l'auteur y échoue ⇒
classe négative) — classe validée par les sondes de difficulté (mono 2/2,
double 2/2, triple 0/1 réparés). Chaque candidate est VÉRIFIÉE zéro-appel
(node --test TAP sur Kimsufi-standard, worktree worldmonitor sérialisé,
restauration git) avant d'entrer au quota ; les invalides sont écartées et
journalisées (jamais de tâche inventée).

Source AGPL : analyse + labels internes seulement — aucun patch répliqué hors
du serveur, les contenus mutés restent locaux à la mesure.
Run: uv run python scripts/act2/ts_v6_quota.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "ts-v6"
HOST = "Kimsufi-standard"
REMOTE = "~/OmniRoute"

MUTANTS = [
    # ---- ancres easy : mutations NEUVES sur fichiers au signal éprouvé (v4/v5) ----
    {"task_id": "omniroute__lite.lookback_window_zeroed", "tier": "ts6-easy",
     "file": "open-sse/services/compression/lite.ts", "test": "tests/unit/8169-lite-word-boundary-truncation.test.ts",
     "replacements": [("const TOOL_TRUNCATION_LOOKBACK = 80;", "const TOOL_TRUNCATION_LOOKBACK = 0;")],
     "problem": "La troncature des résultats d'outils coupe en plein mot : elle ne "
                "cherche plus du tout de frontière de mot en arrière avant de couper."},
    {"task_id": "omniroute__usage.buffer_subtracted_not_added", "tier": "ts6-easy",
     "file": "open-sse/utils/usageTracking.ts", "test": "tests/unit/8331-usage-buffer-inflation.test.ts",
     "replacements": [("result.context_budget_prompt_tokens = result.prompt_tokens + buffer;",
                       "result.context_budget_prompt_tokens = result.prompt_tokens - buffer;")],
     "problem": "Le budget contextuel calculé pour le prompt est inférieur au nombre "
                "réel de tokens au lieu d'inclure la marge de sécurité attendue."},
    {"task_id": "omniroute__affinity.priority_strategy_unrecognized", "tier": "ts6-easy",
     "file": "open-sse/services/combo/promptCacheAffinity.ts", "test": "tests/unit/8370-priority-affinity-reorder.test.ts",
     "replacements": [("strategy === \"priority\" ||", "strategy === \"prioritized\" ||")],
     "problem": "La stratégie de routage 'priority' n'est plus reconnue par la garde "
                "qui protège l'ordre original des identités."},
    # ---- doubles toolResultCompressor (famille neuve omniroute__trc) ----
    {"task_id": "omniroute__trc.double_json_guard_errline", "tier": "ts6-double",
     "file": "open-sse/services/compression/toolResultCompressor.ts", "test": "tests/unit/compression/toolResultCompressor.test.ts",
     "replacements": [("if (arr.length <= 7) return content;", "if (arr.length <= 170) return content;"),
                      ("const errorLine = lines[0] || \"\";", "const errorLine = lines[1] || \"\";")],
     "problem": "Deux anomalies dans le compresseur de résultats d'outils : les grands "
                "tableaux JSON ne sont plus résumés alors qu'ils devraient l'être, et les "
                "messages d'erreur perdent leur première ligne de type dans le résumé."},
    {"task_id": "omniroute__trc.double_shell_dedup_grep_label", "tier": "ts6-double",
     "file": "open-sse/services/compression/toolResultCompressor.ts", "test": "tests/unit/compression/toolResultCompressor.test.ts",
     "replacements": [("line !== deduped[deduped.length - 1]", "line !== deduped[0]"),
                      ("Files: ${[...paths]", "Paths: ${[...paths]")],
     "problem": "Le nettoyage des sorties shell laisse passer des lignes consécutives "
                "identiques au lieu de les regrouper, et le résumé de recherche de code "
                "n'affiche plus la liste des chemins sous l'étiquette attendue."},
    {"task_id": "omniroute__trc.double_keep_lines_json_size", "tier": "ts6-double",
     "file": "open-sse/services/compression/toolResultCompressor.ts", "test": "tests/unit/compression/toolResultCompressor.test.ts",
     "replacements": [("const keep = 20;", "const keep = 2;"),
                      ("if (content.length <= 2000) return null;", "if (content.length >= 2000) return null;")],
     "problem": "Le résumé de contenu code ne conserve plus les premières lignes comme "
                "prévu, et les objets JSON volumineux ne sont plus condensés pendant que "
                "les tout petits le sont à tort."},
    # ---- doubles hardBudget (famille neuve omniroute__hb) ----
    {"task_id": "omniroute__hb.double_preserve_proportional", "tier": "ts6-double",
     "file": "open-sse/services/compression/hardBudget.ts", "test": "tests/unit/compression/hard-budget.test.ts",
     "replacements": [("tagged.filter((x) => !x.preserve)", "tagged.filter((x) => x.preserve)"),
                      ("Math.floor(effectiveTarget * (msgTokens / totalTokens))",
                       "Math.floor(effectiveTarget * (totalTokens / msgTokens))")],
     "problem": "Le post-pass budget dur supprime des lignes sensibles qui devaient être "
                "protégées, et répartit le budget entre messages de telle sorte que "
                "certains reçoivent une marge disproportionnée."},
    {"task_id": "omniroute__hb.double_priority_overbudget", "tier": "ts6-double",
     "file": "open-sse/services/compression/hardBudget.ts", "test": "tests/unit/compression/hard-budget.test.ts",
     "replacements": [("targetTokens != null ? targetTokens : Math.floor(totalTokens * (targetRatio as number))",
                       "targetRatio != null ? Math.floor(totalTokens * (targetRatio as number)) : targetTokens"),
                      ("const overBudget = resultTokens > effectiveTarget;",
                       "const overBudget = resultTokens < effectiveTarget;")],
     "problem": "Quand deux cibles de budget sont fournies ensemble, ce n'est plus la "
                "cible en tokens qui l'emporte, et l'avertissement de budget inatteignable "
                "ne se déclenche plus quand le contenu protégé dépasse la cible."},
    {"task_id": "omniroute__hb.double_early_return_inversions", "tier": "ts6-double",
     "file": "open-sse/services/compression/hardBudget.ts", "test": "tests/unit/compression/hard-budget.test.ts",
     "replacements": [("if (dropped.size === 0) return text;", "if (dropped.size !== 0) return text;"),
                      ("if (units.length <= 1) return text;", "if (units.length <= 10) return text;")],
     "problem": "Le post-pass budget dur renvoie le texte non modifié alors même qu'il a "
                "identifié des unités à supprimer, et il renonce à retravailler des textes "
                "courts de quelques lignes."},
    # ---- seam strategySelector (famille neuve omniroute__seam, deux occurrences) ----
    {"task_id": "omniroute__seam.double_falsy_target_gates", "tier": "ts6-double",
     "file": "open-sse/services/compression/strategySelector.ts", "test": "tests/unit/compression/hard-budget.test.ts",
     "replacements": [("if (options?.config?.targetTokens != null || options?.config?.targetRatio != null) {",
                       "if (options?.config?.targetTokens || options?.config?.targetRatio != null) {"),
                      ("if (options?.config?.targetTokens != null || options?.config?.targetRatio != null) {",
                       "if (options?.config?.targetTokens || options?.config?.targetRatio != null) {")],
     "problem": "Le budget dur ne s'applique plus du tout quand la cible de tokens est "
                "explicitement 0 : le post-pass est silencieusement sauté au lieu de "
                "tenter la compression."},
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
                "instance_id": r["task_id"], "repo": "omniroute",
                "lang": "typescript", "test_runner": "node:test+tsx",
                "tier": r["tier"], "target": r["file"], "spec": r["test"],
                "patch": "", "gold": "",
                "buggy_sha256": sha256(buggy_f.read_bytes()).hexdigest(),
                "f2p": r["f2p"], "p2p_n": r["p2p_n"], "problem": r["problem"],
                "campaign": "coverage-ts-6", "window": "coverage-ts-v6"})
            print(f"  OK : {len(r['f2p'])} F2P, {r['p2p_n']} passés")
        else:
            discarded.append({**r, "discarded_at":
                              datetime.now(UTC).isoformat().replace("+00:00", "Z")})
            print(f"  ÉCARTÉ : {r.get('rejected')}")
    mani = {"window": "coverage-ts-v6", "envelope_calls_cap": 110,
            "probe_calls_already_consumed": 0,  # mis à jour après sonde
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "n_tasks": len(tasks),
            "tiers": {"ts6-easy": sum(1 for t in tasks if t["tier"] == "ts6-easy"),
                      "ts6-double": sum(1 for t in tasks if t["tier"] == "ts6-double")},
            "tasks": tasks}
    (Q / "quota-tasks.json").write_text(json.dumps(mani, indent=1) + "\n")
    with (Q / "discarded.jsonl").open("w") as fh:
        for d in discarded:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"\nquota : {len(tasks)} validées / {len(MUTANTS)} candidates "
          f"({len(discarded)} écartées)")
    if len(tasks) < 10:
        print(f"SHORTFALL vs cible 10 : {10 - len(tasks)} — disclosure à l'exécution")
    return 0


if __name__ == "__main__":
    sys.exit(main())
