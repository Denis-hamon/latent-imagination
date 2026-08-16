#!/usr/bin/env python3
"""Window coverage-ts-v10 — quota PRODUCTION : 17 mutants RÉUTILISÉS (v6/v7/v9,
mêmes définitions, re-validés zéro-appel sur commits épinglés) + 4 triples
NEUFS (DW-35-safe par design : aucun flip de boucle/direction d'itération).
Runners : omniroute node:test TAP, zod/date-fns vitest TAP.
Run: uv run python scripts/act2/ts_v10_quota.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "ts-v10"
HOST = "Kimsufi-standard"

RUNNERS = {
    "omniroute": {"remote": "~/OmniRoute", "leaf": "strip"},
    "zod": {"remote": "~/zod-source",
            "cmd_prefix": "cd ~/zod-source && ",
            "leaf": re.compile(r"^    (not ok|ok) \d+ - (.+?)(?: # time=.*)?$")},
    "date-fns": {"remote": "~/date-fns-source",
                 "cmd_prefix": "cd ~/date-fns-source/pkgs/core && ",
                 "leaf": re.compile(r"^        +(not ok|ok) \d+ - (.+?)(?: # time=.*)?$")},
}

REUSE_IDS = [
    "omniroute__lite.lookback_window_zeroed", "omniroute__usage.buffer_subtracted_not_added",
    "omniroute__affinity.priority_strategy_unrecognized",
    "omniroute__trc.double_json_guard_errline", "omniroute__trc.double_shell_dedup_grep_label",
    "omniroute__hb.double_preserve_proportional", "omniroute__hb.double_priority_overbudget",
    "omniroute__seam.double_falsy_target_gates",
    "zod__checks.double_inclusive_bounds", "zod__checks.double_min_max_bagpair",
    "zod__str.ulid_and_nanoid", "zod__checks.single_max_inclusive",
    "date_fns__bizdays.double_weekend_weeks", "date_fns__addDays.amount_subtracted",
    "omniroute__lite.triple_coordinated", "omniroute__affinity.triple_coordinated",
    "omniroute__usage.triple_coordinated",
]
NEW_TRIPLES = [
    {"task_id": "omniroute__trc.triple_errline_keep_jsonsize", "tier": "ts10-triple",
     "file": "open-sse/services/compression/toolResultCompressor.ts",
     "test": "tests/unit/compression/toolResultCompressor.test.ts",
     "replacements": [("const errorLine = lines[0] || \"\";", "const errorLine = lines[1] || \"\";"),
                      ("const keep = 20;", "const keep = 2;"),
                      ("if (content.length <= 2000) return null;", "if (content.length >= 2000) return null;")],
     "problem": "Trois défauts simultanés dans le compresseur de résultats d'outils : "
                "les messages d'erreur perdent leur ligne de type, les fichiers code "
                "tronqués ne gardent plus leurs premières lignes, et les objets JSON "
                "volumineux ne sont plus condensés pendant que les petits le sont à tort."},
    {"task_id": "omniroute__hb.triple_preserve_proportional_overbudget", "tier": "ts10-triple",
     "file": "open-sse/services/compression/hardBudget.ts", "test": "tests/unit/compression/hard-budget.test.ts",
     "replacements": [("tagged.filter((x) => !x.preserve)", "tagged.filter((x) => x.preserve)"),
                      ("Math.floor(effectiveTarget * (msgTokens / totalTokens))",
                       "Math.floor(effectiveTarget * (totalTokens / msgTokens))"),
                      ("const overBudget = resultTokens > effectiveTarget;",
                       "const overBudget = resultTokens < effectiveTarget;")],
     "problem": "Le post-pass budget dur est triplement cassé : il supprime des lignes "
                "sensibles protégées, répartit le budget de façon disproportionée entre "
                "messages, et l'avertissement de budget inatteignable ne se déclenche plus."},
    {"task_id": "zod__checks.triple_minmax_bag", "tier": "ts10-triple",
     "file": "checks.ts", "test": "number.test.ts",
     "replacements": [("payload.value <= def.value : payload.value < def.value",
                       "payload.value < def.value : payload.value < def.value"),
                      ("payload.value >= def.value : payload.value > def.value",
                       "payload.value > def.value : payload.value > def.value"),
                      ("if (def.value < curr) {\n        if (def.inclusive) bag.maximum = def.value;",
                       "if (def.value > curr) {\n        if (def.inclusive) bag.maximum = def.value;")],
     "problem": "Trois défauts coordonnés dans les contraintes numériques : les bornes "
                "inclusives rejettent la valeur égale dans les deux directions, et "
                "l'agrégation des plafonds successifs ne retient plus la contrainte la plus stricte."},
    {"task_id": "date_fns__bizdays.triple_weeks_ternary_start", "tier": "ts10-triple",
     "file": "differenceInBusinessDays/index.ts", "test": "differenceInBusinessDays/test.ts",
     "replacements": [("let result = weeks * 5;", "let result = weeks * 7;"),
                      ("result += isWeekend(movingDate, options) ? 0 : sign;",
                       "result += isWeekend(movingDate, options) ? sign : 0;"),
                      ("let movingDate = addDays(earlierDate_, weeks * 7);",
                       "let movingDate = addDays(earlierDate_, weeks * 6);")],
     "problem": "Le compte de jours ouvrés est triplement faux : les semaines comptent 7 "
                "jours au lieu de 5 ouvrés, week-ends et jours de semaine sont inversés, "
                "et le parcours démarre au mauvais point de la période."},
]

REPO_OF = lambda tid: "zod" if tid.startswith("zod__") else "date-fns" if tid.startswith("date_fns__") else "omniroute"


def sh_remote(cmd: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                          capture_output=True, text=True, check=False, timeout=timeout)


def run_tests(repo: str, test: str) -> tuple[list[str], int]:
    if repo == "omniroute":
        out = sh_remote(f"cd ~/OmniRoute && timeout 240 node --import tsx/esm --test --test-reporter=tap {test} 2>&1").stdout
        failed, passed = [], 0
        for line in out.splitlines():
            l = line.strip()
            if l.startswith("not ok "):
                failed.append(l[7:].split(" # ")[0].strip())
            elif l.startswith("ok "):
                passed += 1
        return failed, passed
    r = RUNNERS[repo]
    out = sh_remote(f"{r['cmd_prefix']}timeout 240 npx vitest run --reporter=tap {test} 2>&1").stdout
    failed, passed = [], 0
    for line in out.splitlines():
        m = r["leaf"].match(line)
        if m and not line.rstrip().endswith("{"):
            if m.group(1) == "not ok":
                failed.append(m.group(2).split(" > ")[-1].strip())
            else:
                passed += 1
    return failed, passed


def validate(m: dict, repo: str) -> dict:
    r = RUNNERS[repo]
    st = sh_remote(f"cd {r['remote']} && git status --porcelain | head -1")
    if st.stdout.strip():
        return {"task_id": m["task_id"], "rejected": "worktree non propre"}
    orig = sh_remote(f"cd {r['remote']} && cat {m['file']}").stdout
    if not orig.strip():
        return {"task_id": m["task_id"], "rejected": "cat vide"}
    bug = orig
    for old, new in m["replacements"]:
        if old not in bug:
            return {"task_id": m["task_id"], "rejected": f"texte introuvable: {old[:45]}"}
        bug = bug.replace(old, new, 1)
    tmp = Q / f".tmp-{abs(hash(m['task_id'])) % 10**10}.ts"
    tmp.write_text(bug)
    up = subprocess.run(["scp", "-q", str(tmp), f"{HOST}:{r['remote']}/{m['file']}"],
                        capture_output=True, text=True, check=False, timeout=120)
    tmp.unlink(missing_ok=True)
    if up.returncode != 0:
        return {"task_id": m["task_id"], "rejected": "scp échoué"}
    failed, passed = run_tests(repo, m["test"])
    sh_remote(f"cd {r['remote']} && git checkout -- .")
    dirty = sh_remote(f"cd {r['remote']} && git status --porcelain | head -1")
    if dirty.stdout.strip():
        return {"task_id": m["task_id"], "rejected": "restauration a échoué"}
    if not failed:
        return {"task_id": m["task_id"], "rejected": "aucun test ne casse (F2P=0)"}
    return {"task_id": m["task_id"], "ok": True, "buggy": bug,
            "f2p": sorted(set(failed)), "p2p_n": passed,
            "file": m["file"], "test": m["test"], "problem": m["problem"],
            "tier": m["tier"], "repo": repo}


def main() -> int:
    Q.mkdir(parents=True, exist_ok=True)
    allmuts = json.loads(Path("/tmp/tsv6/muts-all.json").read_text())
    # paths fichier/test : les définitions réutilisées ont des chemins complets
    # (v6/v9 omniroute) ou relatifs (v7 zod/date-fns) — normalisation par repo
    MUT = []
    for tid in REUSE_IDS:
        m = allmuts[tid]
        mm = dict(m)
        repo = REPO_OF(tid)
        if repo == "zod" and not mm["file"].startswith("packages/"):
            mm["file"] = f"packages/zod/src/v4/core/{mm['file']}"
            mm["test"] = f"packages/zod/src/v4/classic/tests/{mm['test']}"
        if repo == "date-fns" and not mm["file"].startswith("pkgs/"):
            mm["file"] = f"pkgs/core/src/{mm['file']}"
            # test reste RELATIF à pkgs/core (cmd_prefix y cd déjà)
        tier = mm.get("tier", "")
        mm["tier"] = ("ts10-triple" if "triple" in tid else
                      "ts10-double" if "double" in tier or "double" in tid else "ts10-easy")
        MUT.append(mm)
    for m in NEW_TRIPLES:
        mm = dict(m)
        repo = REPO_OF(mm["task_id"])
        if repo == "zod" and not mm["file"].startswith("packages/"):
            mm["file"] = f"packages/zod/src/v4/core/{mm['file']}"
            mm["test"] = f"packages/zod/src/v4/classic/tests/{mm['test']}"
        if repo == "date-fns" and not mm["file"].startswith("pkgs/"):
            mm["file"] = f"pkgs/core/src/{mm['file']}"
        MUT.append(mm)
    only = set(filter(None, os.environ.get("V10_ONLY", "").split(",")))
    if only:
        MUT = [m for m in MUT if m["task_id"] in only]
    tasks, discarded = [], []
    for m in MUT:
        repo = REPO_OF(m["task_id"])
        print(f"validation {m['tier']:12} {repo:9} {m['task_id'][:52]} …", flush=True)
        r = validate(m, repo)
        if r.pop("ok", False):
            buggy_f = Q / f"{r['task_id'].replace('/', '_')}.buggy.py"
            buggy_f.write_text(r.pop("buggy"))
            tasks.append({"instance_id": r["task_id"], "repo": r["repo"],
                          "lang": "typescript", "tier": r["tier"], "target": r["file"],
                          "spec": r["test"], "patch": "", "gold": "",
                          "buggy_sha256": sha256(buggy_f.read_bytes()).hexdigest(),
                          "f2p": r["f2p"], "p2p_n": r["p2p_n"], "problem": r["problem"],
                          "campaign": "coverage-ts-10", "window": "coverage-ts-v10"})
            print(f"  OK : {len(r['f2p'])} F2P, {r['p2p_n']} P2P")
        else:
            r2 = dict(r); r2.pop("buggy", None)
            discarded.append({**r2, "discarded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")})
            print(f"  ÉCARTÉ : {r.get('rejected')}")
    if only:
        prev = Q / "quota-tasks.json"
        if prev.is_file():
            keep = [t for t in json.loads(prev.read_text())["tasks"] if t["instance_id"] not in only]
            tasks = keep + tasks
    mani = {"window": "coverage-ts-v10", "envelope_calls_cap": 80,
            "probe_calls_already_consumed": 0,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "n_tasks": len(tasks),
            "tiers": {t: sum(1 for x in tasks if x["tier"] == t)
                      for t in ("ts10-triple", "ts10-double", "ts10-easy")},
            "tasks": tasks}
    (Q / "quota-tasks.json").write_text(json.dumps(mani, indent=1) + "\n")
    with (Q / "discarded.jsonl").open("w") as fh:
        for d in discarded:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"\nquota v10 : {len(tasks)} validées / {len(MUT)} candidates ({len(discarded)} écartées)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
