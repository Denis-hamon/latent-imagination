#!/usr/bin/env python3
"""Ré-extraction 2026-08-15 — bug sanitize_diff (ligne de contexte vide → break).

0 call galere : rejoue localement la chaîne d'extraction de one_draw
(extract_full_file + garde 50 % → extract_diff_sanitized corrigé →
apply_and_export_debug) sur les raw-aN.txt persistées des slots classés
no-diff dans les fenêtres s12-gen et s14-gen. Met à jour patch.diff +
meta.json des slots récupérés (champ "reextracted" pour traçabilité).

Un slot récupéré dont le run-result.json decía "pas de diff" doit être
re-labellisé : ce script liste (sans les toucher) les run-results à purger.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"

_spec = importlib.util.spec_from_file_location(
    "pilot_run", ROOT / "scripts" / "act2" / "pilot_run.py")
pr = importlib.util.module_from_spec(_spec)
sys.modules["pilot_run"] = pr
_spec.loader.exec_module(pr)


def _buggy(task_id: str) -> Path | None:
    for d in (PILOT, PILOT / "extension-128"):
        p = d / f"{task_id.replace('/', '_')}.buggy.py"
        if p.is_file():
            return p
    return None


def reextract(stage: str) -> dict:
    results = PILOT / stage / "results"
    recov, unappl, n_checked = [], [], 0
    purge = []
    for mf in sorted(results.glob("*/meta.json")):
        m = json.loads(mf.read_text())
        if m.get("diff_mode") != "no-diff" or m.get("patch_sha256"):
            continue
        slot = mf.parent
        taskf = slot / "task.json"
        if not taskf.is_file():
            continue
        task = json.loads(taskf.read_text())
        bp = _buggy(task["instance_id"])
        if bp is None or not task.get("target"):
            continue
        original = bp.read_text()
        n_checked += 1
        got = None
        for rawf in sorted(slot.glob("raw-a*.txt")):
            if not rawf.stat().st_size:
                continue
            raw = rawf.read_text()
            attempt = int(rawf.stem.split("-a")[1])
            mode = None
            edited = pr.extract_full_file(raw)
            if edited and original and len(edited.splitlines()) < len(original.splitlines()) * 0.5:
                edited = None
            if edited and original and edited.strip() != original.strip():
                got = (pr.make_diff(original, edited, task["target"]),
                       "whole-file", attempt)
                break
            san = pr.extract_diff_sanitized(raw)
            if san and original:
                diff, _err = pr.apply_and_export_debug(
                    original, san + "\n", task["target"])
                if diff:
                    got = (diff, "model-applied-reexport", attempt)
                    break
                mode = "unappliable"
            if mode == "unappliable" and got is None:
                unappl.append(slot.name)
        if got:
            diff, mode, attempt = got
            (slot / "patch.diff").write_text(diff)
            m2 = dict(m)
            m2.update({
                "diff_mode": mode,
                "attempt_used": m.get("attempt_used", attempt),
                "patch_sha256": sha256(diff.encode()).hexdigest(),
                "reextracted": {"at": datetime.now(UTC).isoformat(),
                                "raw": f"raw-a{attempt}.txt",
                                "bug": "sanitize-empty-context-line"},
            })
            mf.write_text(json.dumps(m2, indent=1, sort_keys=True))
            rr = slot / "run-result.json"
            if rr.is_file():
                r = json.loads(rr.read_text())
                if r.get("error") == "pas de diff":
                    purge.append(rr)
            recov.append(slot.name)
    return {"stage": stage, "vérifiés": n_checked, "récupérés": len(recov),
            "unappliable_désormais_explicite": len(set(unappl)),
            "run_results_à_purger": len(purge),
            "_purge": purge, "récupérés_slots": recov}


def main() -> int:
    total = {}
    to_purge = []
    for stage in ("s12-gen", "s14-gen"):
        r = reextract(stage)
        to_purge += r.pop("_purge")
        total[stage] = r
        print(json.dumps(r, indent=1))
    rr = PILOT / "reextract-report.json"
    rr.write_text(json.dumps(total, indent=1))
    # purge des run-results "pas de diff" des slots récupérés → à re-labelliser
    for p in to_purge:
        p.unlink()
    print(f"\npurgés {len(to_purge)} run-results obsolètes (à re-labelliser)")
    print(f"rapport : {rr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
