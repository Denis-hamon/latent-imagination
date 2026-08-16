#!/usr/bin/env python3
"""Window coverage-ts-v5 (quota mixte post-escalade) — builder du quota BI-ÉTAGE sur OmniRoute (MIT).

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
Q = ROOT / "data" / "landing" / "act2-pilot" / "ts-v5"
HOST = "Kimsufi-standard"
REMOTE = "~/OmniRoute"

MUTANTS = [
    # ---- classe easy (positifs attendus ; signal vérifié en v4) ----
    {"task_id": "omniroute__lite.backward_polarity_inverted", "tier": "ts5-easy",
     "file": "open-sse/services/compression/lite.ts", "test": "tests/unit/8169-lite-word-boundary-truncation.test.ts",
     "replacements": [("if (!isWordChar(content[i - 1])) return i - 1;",
                       "if (isWordChar(content[i - 1])) return i - 1;")],
     "problem": "La compression des résultats d'outils coupe des mots en deux : "
                "le texte tronqué se termine au milieu d'un mot au lieu de reculer "
                "jusqu'à la frontière de mot précédente."},
    {"task_id": "omniroute__lite.max_length_raised", "tier": "ts5-easy",
     "file": "open-sse/services/compression/lite.ts", "test": "tests/unit/8169-lite-word-boundary-truncation.test.ts",
     "replacements": [("const MAX_TOOL_LENGTH = 2000;", "const MAX_TOOL_LENGTH = 20000;")],
     "problem": "Les résultats d'outils de quelques milliers de caractères ne sont "
                "plus tronqués alors qu'ils doivent être compressés à ~2000 caractères."},
    {"task_id": "omniroute__affinity.protect_strategy_typo", "tier": "ts5-easy",
     "file": "open-sse/services/combo/promptCacheAffinity.ts", "test": "tests/unit/8370-priority-affinity-reorder.test.ts",
     "replacements": [("strategy === \"weighted\" ||", "strategy === \"weights\" ||")],
     "problem": "La stratégie de routage 'weighted' n'est plus reconnue par la garde "
                "de protection de l'ordre original."},
    {"task_id": "omniroute__usage.buffer_leaks_into_metering", "tier": "ts5-easy",
     "file": "open-sse/utils/usageTracking.ts", "test": "tests/unit/8331-usage-buffer-inflation.test.ts",
     "replacements": [("result.context_budget_prompt_tokens = result.prompt_tokens + buffer;",
                       "result.prompt_tokens = result.prompt_tokens + buffer;")],
     "problem": "Le buffer de sécurité de tokens fuit dans le champ prompt_tokens "
                "visible client : la requête est facturée ~2000 tokens de plus que "
                "le compte réel de l'amont."},
    # ---- classe double (négatifs labellisables attendus : réparation partielle) ----
    {"task_id": "omniroute__lite.double_polarity_maxlen", "tier": "ts5-double",
     "file": "open-sse/services/compression/lite.ts", "test": "tests/unit/8169-lite-word-boundary-truncation.test.ts",
     "replacements": [
         ("if (!isWordChar(content[i - 1])) return i - 1;",
          "if (isWordChar(content[i - 1])) return i - 1;"),
         ("const MAX_TOOL_LENGTH = 2000;", "const MAX_TOOL_LENGTH = 20000;")],
     "problem": "Deux symptômes simultanés dans la compression : certains contenus "
                "longs ne sont plus tronqués du tout, et les troncatures qui ont "
                "lieu coupent en plein mot."},
    {"task_id": "omniroute__lite.double_role_maxlen", "tier": "ts5-double",
     "file": "open-sse/services/compression/lite.ts", "test": "tests/unit/8169-lite-word-boundary-truncation.test.ts",
     "replacements": [
         ("if (msg.role !== \"tool\" || typeof msg.content !== \"string\") return msg;",
          "if (msg.role !== \"assistant\" || typeof msg.content !== \"string\") return msg;"),
         ("const MAX_TOOL_LENGTH = 2000;", "const MAX_TOOL_LENGTH = 20000;")],
     "problem": "La compression des résultats d'outils ne se déclenche plus pour les "
                "messages outils et le seuil de troncature semble décuplé."},
    {"task_id": "omniroute__usage.double_prompt_estimated", "tier": "ts5-double",
     "file": "open-sse/utils/usageTracking.ts", "test": "tests/unit/8331-usage-buffer-inflation.test.ts",
     "replacements": [
         ("result.context_budget_prompt_tokens = result.prompt_tokens + buffer;",
          "result.prompt_tokens = result.prompt_tokens + buffer;"),
         (".estimated === true) {", ".estimated !== true) {")],
     "problem": "Le buffer de sécurité fuit dans prompt_tokens visible client ET "
                "l'exemption prévue pour les usages heuristiques estimés semble "
                "appliquée à l'envers."},
    {"task_id": "omniroute__usage.double_input_total", "tier": "ts5-double",
     "file": "open-sse/utils/usageTracking.ts", "test": "tests/unit/8331-usage-buffer-inflation.test.ts",
     "replacements": [
         ("result.context_budget_input_tokens = result.input_tokens + buffer;",
          "result.input_tokens = result.input_tokens + buffer;"),
         ("result.context_budget_total_tokens = result.total_tokens + buffer;",
          "result.total_tokens = result.total_tokens + buffer;")],
     "problem": "Les champs input_tokens et total_tokens visibles client sont "
                "gonflés du buffer de sécurité au lieu de rester exacts."},
    {"task_id": "omniroute__usage.double_total_estimated", "tier": "ts5-double",
     "file": "open-sse/utils/usageTracking.ts", "test": "tests/unit/8331-usage-buffer-inflation.test.ts",
     "replacements": [
         ("result.context_budget_total_tokens = result.total_tokens + buffer;",
          "result.total_tokens = result.total_tokens + buffer;"),
         (".estimated === true) {", ".estimated !== true) {")],
     "problem": "Le total_tokens client est gonflé du buffer et le régime spécial "
                "des usages estimés ne se comporte plus comme attendu."},
    {"task_id": "omniroute__affinity.double_tiebreak_protect", "tier": "ts5-double",
     "file": "open-sse/services/combo/promptCacheAffinity.ts", "test": "tests/unit/8370-priority-affinity-reorder.test.ts",
     "replacements": [
         ("score === winnerScore && identity < winnerIdentity",
          "score === winnerScore && identity > winnerIdentity"),
         ("strategy === \"weighted\" ||", "strategy === \"weights\" ||")],
     "problem": "Le départage à égalité des identités de cache semble choisir "
                "autrement que prévu, et une stratégie de routage n'est plus "
                "reconnue par la garde de protection."},
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
                "campaign": "coverage-ts-5", "window": "coverage-ts-v5"})
            print(f"  OK : {len(r['f2p'])} F2P, {r['p2p_n']} passés")
        else:
            discarded.append({**r, "discarded_at":
                              datetime.now(UTC).isoformat().replace("+00:00", "Z")})
            print(f"  ÉCARTÉ : {r.get('rejected')}")
    mani = {"window": "coverage-ts-v5", "envelope_calls_cap": 70,
            "probe_calls_already_consumed": 3,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "n_tasks": len(tasks),
            "tiers": {"ts5-easy": sum(1 for t in tasks if t["tier"] == "ts5-easy"),
                      "ts5-double": sum(1 for t in tasks if t["tier"] == "ts5-double")},
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
