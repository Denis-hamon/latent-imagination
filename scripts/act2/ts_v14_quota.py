#!/usr/bin/env python3
"""v14 — quota synthétique date-fns : 3 mutants NEUFS validés zéro-appel
(vitest depuis pkgs/core, feuilles indent>=8) + 4 RÉUTILISÉS des quotas v7/v10
(buggy sha vérifiés). Règle DW-35 : terminaison garantie par design.
Run: uv run python scripts/act2/ts_v14_quota.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "landing" / "act2-pilot" / "ts-v14-datefns"
HOST = "Kimsufi-standard"
REMOTE = "~/date-fns-source"
LEAF = re.compile(r"^ {8,}(not ok|ok) \d+ - (.+?)(?: # time=.*)?$")

NEW = [
    {"task_id": "date_fns__addbizdays.double_weeks_rest", "tier": "df14-double",
     "file": "pkgs/core/src/addBusinessDays/index.ts",
     "test": "addBusinessDays/test.ts",
     "replacements": [("const fullWeeks = Math.trunc(amount / 5);",
                       "const fullWeeks = Math.trunc(amount / 7);"),
                      ("_date.setDate(_date.getDate() + fullWeeks * 7);",
                       "_date.setDate(_date.getDate() + fullWeeks * 5);")],
     "problem": "Le calcul de jours ouvrés additionnés compte mal les semaines complètes : le nombre de semaines est dérivé du mauvais diviseur et le décalage en jours appliqué n'est pas le bon."},
    {"task_id": "date_fns__addbizdays.triple_weeks_weekend_rest", "tier": "df14-triple",
     "file": "pkgs/core/src/addBusinessDays/index.ts",
     "test": "addBusinessDays/test.ts",
     "replacements": [("const fullWeeks = Math.trunc(amount / 5);",
                       "const fullWeeks = Math.trunc(amount / 7);"),
                      ("_date.setDate(_date.getDate() + fullWeeks * 7);",
                       "_date.setDate(_date.getDate() + fullWeeks * 5);"),
                      ("if (!isWeekend(_date, options)) restDays -= 1;",
                       "if (isWeekend(_date, options)) restDays -= 1;")],
     "problem": "L'addition de jours ouvrés est triplement fausse : les semaines complètes sont mal comptées, le décalage appliqué est erroné, et les jours de week-end sont comptés pendant que les jours de semaine sont sautés."},
    {"task_id": "date_fns__setDay.double_day_delta", "tier": "df14-double",
     "file": "pkgs/core/src/setDay/index.ts", "test": "setDay/test.ts",
     "replacements": [("const remainder = day % 7;", "const remainder = day % 5;"),
                      ("const delta = 7 - weekStartsOn;", "const delta = 7 + weekStartsOn;")],
     "problem": "Le réglage d'un jour de la semaine retourne la mauvaise date : le repli du numéro de jour est calculé sur le mauvais cycle, et le décalage lié au premier jour de la semaine est inversé."},
]
NEW += [
    {"task_id": "date_fns__startOfQuarter.double_mod_day", "tier": "df14-double",
     "file": "pkgs/core/src/startOfQuarter/index.ts", "test": "startOfQuarter/test.ts",
     "replacements": [("const month = currentMonth - (currentMonth % 3);",
                       "const month = currentMonth - (currentMonth % 2);"),
                      ("_date.setMonth(month, 1);", "_date.setMonth(month, 2);")],
     "problem": "Le calcul du premier jour du trimestre renvoie le mauvais mois de départ et un jour du mois incorrect."},
    {"task_id": "date_fns__lastDayOfMonth.month_offset", "tier": "df14-easy",
     "file": "pkgs/core/src/lastDayOfMonth/index.ts", "test": "lastDayOfMonth/test.ts",
     "replacements": [("_date.setFullYear(_date.getFullYear(), month + 1, 0);",
                       "_date.setFullYear(_date.getFullYear(), month + 2, 0);")],
     "problem": "Le dernier jour du mois renvoie une date située dans le mois suivant."},
    {"task_id": "date_fns__addWeeks.days_factor", "tier": "df14-easy",
     "file": "pkgs/core/src/addWeeks/index.ts", "test": "addWeeks/test.ts",
     "replacements": [("return addDays(date, amount * 7, options);",
                       "return addDays(date, amount * 5, options);")],
     "problem": "Ajouter des semaines décale la date du mauvais nombre de jours par semaine."},
]

REUSE = [
    ("date_fns__bizdays.double_weekend_weeks", "ts-v7"),
    ("date_fns__bizdays.weekend_counted", "ts-v7"),
    ("date_fns__addDays.amount_subtracted", "ts-v7"),
    ("date_fns__bizdays.triple_weeks_ternary_start", "ts-v10"),
]


def sh(cmd: str, t: int = 600) -> str:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                          capture_output=True, text=True, check=False, timeout=t).stdout


def vitest(test_rel: str) -> tuple[list[str], int]:
    out = sh(f"cd {REMOTE}/pkgs/core && timeout 240 npx vitest run --no-cache --reporter=tap src/{test_rel} 2>&1")
    failed, passed = [], 0
    for line in out.splitlines():
        m = LEAF.match(line)
        if m and not line.rstrip().endswith("{"):
            if m.group(1) == "not ok":
                failed.append(m.group(2).split(" > ")[-1].strip())
            else:
                passed += 1
    return failed, passed


def validate(m: dict) -> dict:
    st = sh(f"cd {REMOTE} && git status --porcelain | head -1")
    if st.strip():
        return {"task_id": m["task_id"], "rejected": "worktree non propre"}
    orig = sh(f"cd {REMOTE} && cat {m['file']}")
    if not orig.strip():
        return {"task_id": m["task_id"], "rejected": "cat vide"}
    bug = orig
    for old, new in m["replacements"]:
        if old not in bug:
            return {"task_id": m["task_id"], "rejected": f"texte introuvable: {old[:45]}"}
        bug = bug.replace(old, new, 1)
    tmp = OUT / f".tmp-{abs(hash(m['task_id'])) % 10**8}.ts"
    tmp.write_text(bug)
    subprocess.run(["scp", "-q", str(tmp), f"{HOST}:{REMOTE}/{m['file']}"],
                   capture_output=True, check=False, timeout=120)
    tmp.unlink(missing_ok=True)
    failed, passed = vitest(m["test"])
    sh(f"cd {REMOTE} && git checkout -- . && git status --porcelain | wc -l")
    if not failed:
        return {"task_id": m["task_id"], "rejected": "aucun test ne casse (F2P=0)"}
    return {"task_id": m["task_id"], "ok": True, "buggy": bug, "f2p": sorted(set(failed)),
            "p2p_n": passed, "file": m["file"], "test": m["test"],
            "problem": m["problem"], "tier": m["tier"]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tasks, discarded = [], []
    for m in NEW:
        print(f"validation {m['tier']:12} {m['task_id']}", flush=True)
        r = validate(m)
        if r.pop("ok", False):
            buggy = r.pop("buggy")
            bf = OUT / f"{r['task_id'].replace('/', '_')}.buggy.py"
            bf.write_text(buggy)
            tasks.append({"instance_id": r["task_id"], "tier": r["tier"], "repo": "date-fns",
                          "target": r["file"], "spec": r["test"],
                          "buggy_sha256": sha256(bf.read_bytes()).hexdigest(),
                          "f2p": r["f2p"], "p2p_n": r["p2p_n"], "problem": r["problem"],
                          "campaign": "coverage-ts-v14-datefns", "window": "coverage-ts-v14"})
            print(f"  OK : {len(r['f2p'])} F2P, {r['p2p_n']} P2P")
        else:
            r.pop("buggy", None)
            discarded.append(r)
            print(f"  ÉCARTÉ : {r.get('rejected')}")
    for iid, src_dir in REUSE:
        src_q = ROOT / "data" / "landing" / "act2-pilot" / src_dir
        bf_src = src_q / f"{iid.replace('/', '_')}.buggy.py"  # noqa: E501
        mani = json.loads((src_q / "quota-tasks.json").read_text())
        t0 = next((t for t in mani["tasks"] if t["instance_id"] == iid), None)
        if t0 is None or not bf_src.is_file():
            discarded.append({"task_id": iid, "rejected": "source réutilisable introuvable"})
            continue
        shutil.copy(bf_src, OUT / bf_src.name)
        tasks.append({"instance_id": iid, "tier": t0["tier"] + "-reuse", "repo": "date-fns",
                      "target": t0["target"], "spec": t0["spec"],
                      "buggy_sha256": t0["buggy_sha256"], "f2p": t0["f2p"],
                      "p2p_n": t0["p2p_n"], "problem": t0["problem"],
                      "campaign": "coverage-ts-v14-datefns", "window": "coverage-ts-v14"})
        print(f"réutilisé : {iid} ({len(t0['f2p'])} F2P)")
    mani_out = {"window": "coverage-ts-v14", "envelope": "v14 global 400 (flash 320/qwen 80)",
                "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "n_tasks": len(tasks), "tasks": tasks}
    (OUT / "quota-tasks.json").write_text(json.dumps(mani_out, indent=1) + "\n")
    with (OUT / "discarded.jsonl").open("w") as fh:
        for d in discarded:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"quota date-fns v14 : {len(tasks)} tâches ({len(discarded)} écartées)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
