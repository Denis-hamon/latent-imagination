#!/usr/bin/env python3
"""Story 10.1 — récupération OFFLINE des slots no-diff (zéro nouvel appel).

Rejoue les raw replies déjà persistées dans call-log.jsonl sur les slots au
statut "no-diff" : lane stricte (git apply) puis lane fuzz (patch --fuzz=3 +
ré-export git, lignage sanitize 3516b5e). Un diff récupéré met à jour rec.json
(status ok, diff_mode recovered-*) et écrit diff.patch. Les slots qui restent
no-diff après les DEUX lanes sont exhaustés — disclosés au rapport, jamais
relancés par de nouveaux appels (discipline d'enveloppe).

Usage après un HALT diagnostic : uv run python scripts/act2/genfam_recover.py --quota q1
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOBS = ROOT / "data" / "landing" / "act2-pilot"

_spec = importlib.util.spec_from_file_location("pilot_run", ROOT / "scripts" / "act2" / "pilot_run.py")
pr = importlib.util.module_from_spec(_spec)
sys.modules["pilot_run"] = pr
_spec.loader.exec_module(pr)

_gen_spec = importlib.util.spec_from_file_location("genfam_gen", ROOT / "scripts" / "act2" / "genfam_gen.py")
gg = importlib.util.module_from_spec(_gen_spec)
_gen_spec.loader.exec_module(gg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quota", choices=("q1", "q2"), default="q1")
    args = ap.parse_args()
    qdir = JOBS / f"genfam-{args.quota}"
    log = qdir / "call-log.jsonl"
    results = qdir / "gen-results"
    if not log.is_file() or not results.is_dir():
        print("call-log ou gen-results absent — rien à récupérer")
        return 1

    raw_by_slot: dict[str, list[str]] = {}
    for line in log.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("slot") and d.get("raw_reply"):
            raw_by_slot.setdefault(d["slot"], []).append(d["raw_reply"])

    recovered = still_nodiff = 0
    modes: dict[str, int] = {}
    for rec_path in sorted(results.glob("*/rec.json")):
        rec = json.loads(rec_path.read_text())
        if rec["status"] != "no-diff":
            continue
        work = rec_path.parent
        buggy_path = qdir / f"{rec['task'].replace('/', '_')}.buggy.py"
        task_path = work / "task.json"
        if not buggy_path.is_file() or not task_path.is_file():
            still_nodiff += 1
            continue
        original = buggy_path.read_text()
        target = json.loads(task_path.read_text())["target"]
        slot = rec["slot"]
        diff = None
        for raw in raw_by_slot.get(slot, []):
            edited = pr.extract_full_file(raw)
            if (edited and edited.strip() != original.strip()
                    and len(edited.splitlines()) >= len(original.splitlines()) * 0.5):
                diff = pr.make_diff(original, edited, target)
                if diff:
                    rec["diff_mode"] = "recovered-whole-file"
                    break
            san = pr.extract_diff_sanitized(raw)
            if not san:
                continue
            diff, _e = pr.apply_and_export_debug(original, san + "\n", target)
            if diff:
                rec["diff_mode"] = "recovered-strict"
                break
            diff, _e2 = gg.apply_fuzz_reexport(original, san + "\n", target)
            if diff:
                rec["diff_mode"] = "recovered-fuzz"
                break
        if diff:
            from hashlib import sha256
            recovered += 1
            modes[rec["diff_mode"]] = modes.get(rec["diff_mode"], 0) + 1
            (work / "diff.patch").write_text(diff)
            rec["status"] = "ok"
            rec["diff_sha256"] = sha256(diff.encode()).hexdigest()
            rec_path.write_text(json.dumps(rec, indent=1))
        else:
            still_nodiff += 1
    report = {"quota": args.quota, "recovered": recovered,
              "still_no_diff": still_nodiff, "modes": modes,
              "note": "récupération offline depuis call-log ; zéro nouvel appel modèle"}
    out = results / "recover-report.json"
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(f"récupérés: {recovered} | toujours no-diff (exhaustés): {still_nodiff} | modes: {modes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
