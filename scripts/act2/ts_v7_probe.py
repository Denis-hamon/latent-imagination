#!/usr/bin/env python3
"""Window coverage-ts-v7 — SONDE PRÉ-GEL : 2 candidats doubles sur fichiers
NEUFS (toolResultCompressor, hardBudget) × 2 tirages = 4 appels max, comptés
à l'enveloppe v6 (cap 110). Règle gelée (doc fenêtre) : ≥1 tirage par fichier
produit un diff applicable ⇒ fichier validé ; 2/2 no-diff ⇒ SWAP de fichier
(même classe), jamais forçage. La classe double est déjà validée en v5 — la
sonde valide uniquement les nouveaux fichiers.
Vérification zéro-appel des candidats : déjà faite par ts_v6_quota.py
(quota-tasks.json + buggy files dans ts-v6/).
Run: uv run python scripts/act2/ts_v6_probe.py --stage author
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "ts-v7"
CAMPAIGN = "coverage-ts-7"

PROBE_TASKS = [
    "zod__checks.double_string_minmax_length",
    "date_fns__bizdays.double_weekend_weeks",
]
DRAWS = 2


def author_stage() -> int:
    mani = json.loads((Q / "quota-tasks.json").read_text())
    by_id = {t["instance_id"]: t for t in mani["tasks"]}
    spec = importlib.util.spec_from_file_location("gg", ROOT / "scripts" / "act2" / "genfam_gen.py")
    gg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gg)
    spec2 = importlib.util.spec_from_file_location("pr2", ROOT / "scripts" / "act2" / "pilot_run.py")
    pr = importlib.util.module_from_spec(spec2)
    sys.modules["pilot_run"] = pr
    spec2.loader.exec_module(pr)
    pr.call_model = gg.call_t07
    os.environ["PILOT_CAMPAIGN_DIR"] = CAMPAIGN
    pr.os.environ["PILOT_CAMPAIGN_DIR"] = CAMPAIGN
    (ROOT / "data/landing/act2-pilot" / CAMPAIGN).mkdir(parents=True, exist_ok=True)
    log = ROOT / "data/landing/act2-pilot" / CAMPAIGN / "call-log.jsonl"
    results = {}
    for tid in PROBE_TASKS:
        t = by_id[tid]
        results[tid] = {"draws": []}
        buggy = (Q / f"{tid.replace('/', '_')}.buggy.py").read_text()
        for d in range(1, DRAWS + 1):
            task = {"instance_id": tid, "problem": t["problem"],
                    "f2p": t["f2p"][:6], "target": t["target"]}
            try:
                g = pr.gen_patch(task)
                err = None
            except Exception as e:  # noqa: BLE001 — erreur endpoint auditée
                g, err = None, str(e)[:300]
            row = {"ts": datetime.now(UTC).isoformat(), "window": "coverage-ts-v7",
                   "stage": "difficulty-probe", "slot": f"{tid}-d{d}",
                   "model": gg.MODEL, "campaign": CAMPAIGN, "temperature": 0.7}
            if err:
                row["error"] = err
            else:
                row.update({"prompt_sha256": g["prompt_sha256"],
                            "reply_sha256": g["reply_sha256"],
                            "raw_reply": g["raw_reply"], "usage": g["usage"]})
                san = pr.extract_diff_sanitized(g["raw_reply"])
                diff = mode = None
                if san:
                    diff, _e = pr.apply_and_export_debug(buggy, san + "\n", t["target"])
                    mode = "strict-git" if diff else None
                    if diff is None:
                        diff, _e2 = gg.apply_fuzz_reexport(buggy, san + "\n", t["target"])
                        mode = "fuzz-reexport" if diff else None
                row.update({"diff_mode": mode,
                            "diff_sha256": sha256(diff.encode()).hexdigest() if diff else None})
                if diff:
                    (Q / f"{tid.replace('/', '_')}-probe-d{d}.diff").write_text(diff)
            with log.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            got = bool(row.get("diff_sha256"))
            results[tid]["draws"].append({"draw": d, "diff": got, "mode": row.get("diff_mode"),
                                          "error": row.get("error")})
            print(f"{tid} d{d}: " + (f"diff ({row.get('diff_mode')})" if got else
                  f"PAS DE DIFF{' (err)' if err else ' (no-diff)'}"), flush=True)
    verdicts = {}
    for tid, r in results.items():
        n = sum(1 for x in r["draws"] if x["diff"])
        verdicts[tid] = {
            "n_applicable": n, "n_draws": len(r["draws"]),
            "verdict": ("FICHIER VALIDÉ (>=1 diff applicable)" if n >= 1
                        else "2/2 no-diff ⇒ SWAP de fichier requis (règle gelée)"),
        }
    (Q / "probe-verdict-v6.json").write_text(json.dumps(
        {"window": "coverage-ts-v7", "campaign": CAMPAIGN,
         "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
         "rule": ">=1 tirage par fichier produit un diff applicable => fichier validé; "
                 "2/2 no-diff => swap fichier, jamais forçage",
         "results": verdicts,
         "probe_calls": sum(len(r["draws"]) for r in results.values())},
        indent=1) + "\n")
    for tid, v in verdicts.items():
        print(f"SONDE {tid}: {v['n_applicable']}/{v['n_draws']} ⇒ {v['verdict']}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("author",), required=True)
    ap.parse_args()
    sys.exit(author_stage())
