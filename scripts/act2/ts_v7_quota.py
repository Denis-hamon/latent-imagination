#!/usr/bin/env python3
"""Window coverage-ts-v7 (négatifs-first multi-sources) — builder du quota :
candidats vérifiés zéro-appel sur zod (MIT) + date-fns (MIT), runners vitest.
RÈGLE NEUVE scellée (DW-35) : un mutant ne doit jamais pouvoir créer une
boucle non terminante (terminaison vérifiée à la conception).
Run: uv run python scripts/act2/ts_v7_quota.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "ts-v7"
HOST = "Kimsufi-standard"

RUNNERS = {
    "zod": {
        "remote": "~/zod-source",
        "cmd": "cd ~/zod-source && npx vitest run --reporter=tap packages/zod/src/v4/classic/tests/{test} 2>&1",
        "leaf": re.compile(r"^    (not ok|ok) \d+ - (.+?)(?: # time=.*)?$"),
        "file_prefix": "packages/zod/src/v4/core/",
    },
    "date-fns": {
        "remote": "~/date-fns-source",
        "cmd": "cd ~/date-fns-source/pkgs/core && npx vitest run --reporter=tap src/{test} 2>&1",
        "leaf": re.compile(r"^        +(not ok|ok) \d+ - (.+?)(?: # time=.*)?$"),
        "file_prefix": "pkgs/core/src/",
    },
}

MUTANTS = [
    # ================= zod (famille zod__checks / zod__str) =================
    {"task_id": "zod__checks.double_inclusive_bounds", "tier": "ts7-double", "repo": "zod",
     "replacements": [("payload.value <= def.value : payload.value < def.value",
                       "payload.value < def.value : payload.value < def.value"),
                      ("payload.value >= def.value : payload.value > def.value",
                       "payload.value > def.value : payload.value > def.value")],
     "file": "checks.ts", "test": "number.test.ts",
     "problem": "Les bornes numériques inclusives (.min/.max/.lte/.gte) rejettent la valeur égale à la borne au lieu de l'accepter."},
    {"task_id": "zod__checks.bound_and_tightening", "tier": "ts7-double", "repo": "zod",
     "replacements": [("payload.value <= def.value : payload.value < def.value",
                       "payload.value < def.value : payload.value < def.value"),
                      ("if (def.value < curr) {\n        if (def.inclusive) bag.maximum = def.value;",
                       "if (def.value > curr) {\n        if (def.inclusive) bag.maximum = def.value;")],
     "file": "checks.ts", "test": "number.test.ts",
     "problem": "La contrainte de plafond numérique n'est plus resserrée quand une borne plus stricte s'ajoute, et la borne inclusive rejette la valeur égale."},
    {"task_id": "zod__checks.double_min_max_bagpair", "tier": "ts7-double", "repo": "zod",
     "replacements": [("payload.value >= def.value : payload.value > def.value",
                       "payload.value > def.value : payload.value > def.value"),
                      ("if (def.value < curr) {\n        if (def.inclusive) bag.maximum = def.value;",
                       "if (def.value > curr) {\n        if (def.inclusive) bag.maximum = def.value;")],
     "file": "checks.ts", "test": "number.test.ts",
     "problem": "Une borne plancher inclusive rejette la valeur égale, et l'agrégation des plafonds successifs ne retient plus la contrainte la plus stricte."},
    {"task_id": "zod__checks.double_string_minmax_length", "tier": "ts7-double", "repo": "zod",
     "replacements": [("if (length <= def.maximum) return;", "if (length < def.maximum) return;"),
                      ("if (length >= def.minimum) return;", "if (length > def.minimum) return;")],
     "file": "checks.ts", "test": "string.test.ts",
     "problem": "Les bornes de longueur de chaîne inclusives rejettent les textes de longueur exactement égale à la limite, dans les deux directions."},
    {"task_id": "zod__str.ulid_and_nanoid", "tier": "ts7-double", "repo": "zod",
     "replacements": [("/^[0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{26}$/;",
                       "/^[0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{25}$/;"),
                      ("/^[a-zA-Z0-9_-]{21}$/;", "/^[a-zA-Z0-9_-]{22}$/;")],
     "file": "regexes.ts", "test": "string.test.ts",
     "problem": "Les identifiants ULID valides sont refusés tandis que les nanoids de longueur invalide passent la validation."},
    {"task_id": "zod__checks.single_max_inclusive", "tier": "ts7-easy", "repo": "zod",
     "replacements": [("payload.value <= def.value : payload.value < def.value",
                       "payload.value < def.value : payload.value < def.value")],
     "file": "checks.ts", "test": "number.test.ts",
     "problem": "Un plafond numérique inclusif rejette la valeur exactement égale à la limite."},
    # ================= date-fns (famille date_fns__bizdays / addDays) =================
    {"task_id": "date_fns__bizdays.double_weekend_weeks", "tier": "ts7-double", "repo": "date-fns",
     "replacements": [("result += isWeekend(movingDate, options) ? 0 : sign;",
                       "result += isWeekend(movingDate, options) ? sign : 0;"),
                      ("let result = weeks * 5;", "let result = weeks * 7;")],
     "file": "differenceInBusinessDays/index.ts", "test": "differenceInBusinessDays/test.ts",
     "problem": "Le compte de jours ouvrés traite les week-ends comme des jours travaillés et en ignore les jours de semaine, tout en comptant les semaines pleines à 7 jours."},
    {"task_id": "date_fns__bizdays.double_round_weekend", "tier": "ts7-double", "repo": "date-fns",
     "replacements": [("result += isWeekend(movingDate, options) ? 0 : sign;",
                       "result += isWeekend(movingDate, options) ? sign : 0;"),
                      ("const weeks = Math.trunc(diff / 7);", "const weeks = Math.round(diff / 7);")],
     "file": "differenceInBusinessDays/index.ts", "test": "differenceInBusinessDays/test.ts",
     "problem": "Le compte de jours ouvrés inverse week-ends et jours travaillés, et arrondit les semaines complètes au plus proche au lieu de les tronquer."},
    {"task_id": "date_fns__bizdays.weekend_counted", "tier": "ts7-easy", "repo": "date-fns",
     "replacements": [("result += isWeekend(movingDate, options) ? 0 : sign;",
                       "result += isWeekend(movingDate, options) ? sign : 0;")],
     "file": "differenceInBusinessDays/index.ts", "test": "differenceInBusinessDays/test.ts",
     "problem": "Le calcul de jours ouvrés compte les jours de week-end et ignore les jours de semaine."},
    {"task_id": "date_fns__addDays.amount_subtracted", "tier": "ts7-easy", "repo": "date-fns",
     "replacements": [("_date.setDate(_date.getDate() + amount);",
                       "_date.setDate(_date.getDate() - amount);")],
     "file": "addDays/index.ts", "test": "addDays/test.ts",
     "problem": "Ajouter un nombre de jours à une date la décale en arrière au lieu d'avancer."},
]


def sh_remote(cmd: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                          capture_output=True, text=True, check=False, timeout=timeout)


def vitest(repo: str, test: str) -> tuple[list[str], int]:
    r = RUNNERS[repo]
    out = sh_remote(r["cmd"].format(test=test)).stdout
    failed, passed = [], 0
    for line in out.splitlines():
        m = r["leaf"].match(line)
        if m and not line.rstrip().endswith("{"):
            if m.group(1) == "not ok":
                failed.append(m.group(2).split(" > ")[-1].strip())
            else:
                passed += 1
    return failed, passed


def validate(m: dict) -> dict:
    r = RUNNERS[m["repo"]]
    st = sh_remote(f"cd {r['remote']} && git status --porcelain | head -1")
    if st.stdout.strip():
        return {"task_id": m["task_id"], "rejected": "worktree non propre"}
    files = m.get("files") or {m["file"]: m["replacements"]}
    bugs, paths = {}, {}
    try:
        for f, repls in files.items():
            path = r["file_prefix"] + f if m["repo"] == "zod" else f"pkgs/core/src/{f}"
            bug = sh_remote(f"cd {r['remote']} && cat {path}").stdout
            if not bug.strip():
                return {"task_id": m["task_id"], "rejected": f"cat vide {path}"}
            for old, new in repls:
                if old not in bug:
                    return {"task_id": m["task_id"], "rejected": f"texte introuvable dans {f}: {old[:50]}"}
                bug = bug.replace(old, new, 1)
            bugs[f] = bug
            paths[f] = path
        for f, bug in bugs.items():
            tmp = Q / f".tmp-{m['task_id'][-8:]}-{abs(hash(f)) % 10**6}.ts"
            tmp.write_text(bug)
            up = subprocess.run(["scp", "-q", str(tmp), f"{HOST}:{r['remote']}/{paths[f]}"],
                                capture_output=True, text=True, check=False, timeout=120)
            tmp.unlink(missing_ok=True)
            if up.returncode != 0:
                return {"task_id": m["task_id"], "rejected": "scp échoué"}
        failed, passed = vitest(m["repo"], m["test"])
        # buggy sources : premier fichier seulement conservé comme .buggy.py
        # (les multi-fichiers sont gérés par la map files du manifeste)
        buggy = next(iter(bugs.values()))
    except Exception as exc:  # noqa: BLE001 — erreur ssh/scp auditée
        sh_remote(f"cd {r['remote']} && git checkout -- .")
        return {"task_id": m["task_id"], "rejected": f"erreur: {str(exc)[:80]}"}
    sh_remote(f"cd {r['remote']} && git checkout -- .")
    dirty = sh_remote(f"cd {r['remote']} && git status --porcelain | head -1")
    if dirty.stdout.strip():
        return {"task_id": m["task_id"], "rejected": "restauration a échoué — WORKTREE DIRTY"}
    if not failed:
        return {"task_id": m["task_id"], "rejected": "aucun test ne casse (F2P=0)"}
    return {"task_id": m["task_id"], "ok": True, "buggy": buggy,
            "files": {f: bugs[f] for f in bugs},
            "f2p": sorted(set(failed)), "p2p_n": passed,
            "repo": m["repo"], "file": m["file"], "test": m["test"],
            "problem": m["problem"], "tier": m["tier"]}


def main() -> int:
    Q.mkdir(parents=True, exist_ok=True)
    tasks, discarded = [], []
    for m in MUTANTS:
        print(f"validation {m['tier']:10} {m['repo']:8} {m['task_id']} …", flush=True)
        r = validate(m)
        if r.pop("ok", False):
            r.pop("files", None)
            buggy_f = Q / f"{r['task_id'].replace('/', '_')}.buggy.py"
            buggy_f.write_text(r.pop("buggy"))
            tasks.append({
                "instance_id": r["task_id"], "repo": r["repo"],
                "lang": "typescript", "test_runner": "vitest", "tier": r["tier"],
                "target": (RUNNERS[r["repo"]]["file_prefix"] + r["file"]) if r["repo"] == "zod"
                          else f"pkgs/core/src/{r['file']}",
                "spec": r["test"], "patch": "", "gold": "",
                "buggy_sha256": sha256(buggy_f.read_bytes()).hexdigest(),
                "f2p": r["f2p"], "p2p_n": r["p2p_n"], "problem": r["problem"],
                "campaign": "coverage-ts-7", "window": "coverage-ts-v7"})
            print(f"  OK : {len(r['f2p'])} F2P, {r['p2p_n']} P2P")
        else:
            r.pop("files", None); r.pop("buggy", None)
            discarded.append({**r, "discarded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")})
            print(f"  ÉCARTÉ : {r.get('rejected')}")
    mani = {"window": "coverage-ts-v7", "envelope_calls_cap": 95,
            "probe_calls_already_consumed": 0,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "n_tasks": len(tasks),
            "tiers": {t: sum(1 for x in tasks if x["tier"] == t) for t in ("ts7-double", "ts7-easy")},
            "tasks": tasks}
    (Q / "quota-tasks.json").write_text(json.dumps(mani, indent=1) + "\n")
    with (Q / "discarded.jsonl").open("w") as fh:
        for d in discarded:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"\nquota v7 : {len(tasks)} validées / {len(MUTANTS)} candidates ({len(discarded)} écartées)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
