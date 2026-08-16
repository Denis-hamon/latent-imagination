#!/usr/bin/env python3
"""Story 10.2 — classification genfam : labels rules-v1 depuis la preuve brute.

Offline, déterministe, juge unique = rules_v1 (packages/labeling). Sépare la
mesure (genfam_label_exec.py, docker) de l'adjudication (ce script) : les
labels restent re-dérivables des raw traces (FR-3).

Précédent gelé (s12_pool.py:8) : y=1 ssi f2p_pass ET (p2p_pass OU p2p non
déclaré). Un P2P déclaré qui échoue est un VETO (le fix casse des tests qui
passaient) → jamais VALID_EXECUTION.

Taxonomie :
- chaîne non mesurable (erreur docker / bug ou patch inappliqués) → quarantine
  ENVIRONMENT_UNDETERMINED (hors numérateur ET dénominateur) ;
- sortie F2P ambiguë selon rules_v1 (None) → quarantine AMBIGUOUS_OUTPUT ;
- sinon label LabelOutcome : VALID_EXECUTION (y=1), FALSE_START_INFRASTRUCTURE_
  FAILURE (rules_v1 infra), FALSE_START_TESTS_RAN_NO_FLIP (y=0) ;
- part de quarantaine > 10 % → REFUS d'émettre (LI-LABEL-001), jamais
  d'abaissement silencieux du cap.

Sorties (genfam-q1/labels/) :
- labels-rules-v1.json : Label dicts purs {attempt_id, outcome, schema_version,
  ruleset_version, evidence_ref}, tri par attempt_id ;
- quarantine-rules-v1.json : QuarantineRecord dicts ;
- genfam-label-report.json : couche occurrence/provenance (campaign, window,
  author, y, audit cap, compte par famille).

Run: uv run python scripts/act2/genfam_label_build.py --quota q1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "labeling" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "core-schema" / "src"))

from labeling.rules_v1 import (
    RULESET_VERSION,
    SCHEMA_VERSION,
    classify_tests_output,
)

QUARANTINE_CAP = 0.10


def _label(attempt_id: str, outcome: str, evidence_ref: str) -> dict:
    return {"attempt_id": attempt_id, "outcome": outcome,
            "schema_version": SCHEMA_VERSION, "ruleset_version": RULESET_VERSION,
            "evidence_ref": evidence_ref}


def _quarantine(attempt_id: str, reason: str, trace_ref: str) -> dict:
    return {"attempt_id": attempt_id, "reason_code": reason,
            "rule_ids": (["R-env-1"] if reason == "environment_undetermined"
                         else ["R-amb-1"]),
            "trace_ref": trace_ref}


def classify_slot(rr: dict, evidence_ref: str) -> tuple[dict | None, dict | None, int | None]:
    """Retourne (label, quarantine, y) — exactement un des deux premiers est non-None."""
    attempt = rr["slot"]
    if rr.get("error") or not rr.get("bug_applied") or not rr.get("patch_applied"):
        return None, _quarantine(attempt, "environment_undetermined", evidence_ref), None
    f2p_tail = rr.get("f2p_tail", "")
    cls = classify_tests_output(f2p_tail)
    if cls is None:
        return None, _quarantine(attempt, "ambiguous_output", evidence_ref), None
    f2p_ok = rr.get("f2p_rc") == 0
    f2p_declared = "f2p_rc" in rr
    if not f2p_declared:
        return None, _quarantine(attempt, "environment_undetermined", evidence_ref), None
    if f2p_ok:
        if "p2p_rc" not in rr:
            # p2p déclarés, f2p verts, mais la chaîne n'a pas produit de P2P :
            # interruption ≠ absence de P2P → non mesurable, jamais deviné
            return None, _quarantine(attempt, "environment_undetermined", evidence_ref), None
        p2p_ok = rr["p2p_rc"] == 0 or rr["p2p_rc"] is None  # None = non déclarés ⇒ pas de veto
        y = 1 if p2p_ok else 0
    else:
        y = 0
    if y == 1:
        outcome = "valid_execution"
    elif cls.value == "false_start_infrastructure_failure":
        outcome = cls.value
    else:
        outcome = "false_start_tests_ran_no_flip"
    return _label(attempt, outcome, evidence_ref), None, y


def build(qdir: Path) -> tuple[int, dict]:
    """Cœur déterministe (testable sans disk layout réel): lit qdir/gen-results,
    écrit qdir/labels. Retourne (exit_code, résumé)."""
    results = qdir / "gen-results"
    out_dir = qdir / "labels"
    out_dir.mkdir(parents=True, exist_ok=True)

    labels, quarantines, provenance = [], [], []
    for rr_path in sorted(results.glob("*/run-result.json")):
        rr = json.loads(rr_path.read_text())
        rel = str(rr_path.relative_to(qdir))
        lbl, q, y = classify_slot(rr, rel)
        rec = rr
        prov = {"attempt_id": rec["slot"], "task": rec.get("task"),
                "campaign": rec.get("campaign"), "window": rec.get("window"),
                "author": rec.get("author"), "draw": rec.get("draw"),
                "diff_sha256": rec.get("diff_sha256"),
                "evidence_ref": rel}
        if lbl:
            labels.append(lbl)
            prov["y"] = y
            prov["layer"] = "label"
        else:
            quarantines.append(q)
            prov["y"] = None
            prov["layer"] = "quarantine"
            prov["reason_code"] = q["reason_code"]
        provenance.append(prov)

    total = len(labels) + len(quarantines)
    share = (len(quarantines) / total) if total else 0.0
    if total == 0:
        return 1, {"status": "EMPTY",
                   "note": "aucun run-result.json — la mesure docker doit tourner d'abord"}
    if share > QUARANTINE_CAP:
        (out_dir / "genfam-label-report.json").write_text(json.dumps({
            "status": "REFUSED", "quarantine_share": round(share, 4),
            "cap": QUARANTINE_CAP, "labels": len(labels), "quarantines": len(quarantines),
            "note": "cap de quarantaine dépassé — labels non émis; diagnostiquer la "
                    "chaîne docker (LI-LABEL-001), jamais abaisser le cap en silence"},
            indent=1) + "\n")
        return 2, {"status": "REFUSED", "quarantine_share": round(share, 4),
                   "cap": QUARANTINE_CAP, "labels": len(labels),
                   "quarantines": len(quarantines)}

    labels.sort(key=lambda r: r["attempt_id"])
    (out_dir / "labels-rules-v1.json").write_text(
        json.dumps(labels, sort_keys=True, separators=(",", ":")) + "\n")
    quarantines.sort(key=lambda r: r["attempt_id"])
    (out_dir / "quarantine-rules-v1.json").write_text(
        json.dumps(quarantines, sort_keys=True, separators=(",", ":")) + "\n")

    by_fam: dict[str, dict[str, int]] = {}
    for p in provenance:
        fam = (p["task"] or "?").split(".")[0]
        b = by_fam.setdefault(fam, {"labels": 0, "y1": 0, "quarantine": 0})
        if p["layer"] == "label":
            b["labels"] += 1
            b["y1"] += 1 if p["y"] == 1 else 0
        else:
            b["quarantine"] += 1
    report = {"quota": qdir.name.removeprefix("genfam-"), "ruleset_version": RULESET_VERSION,
              "total_measured": total, "labels": len(labels),
              "y1": sum(1 for p in provenance if p.get("y") == 1),
              "y0": sum(1 for p in provenance if p.get("y") == 0),
              "quarantines": len(quarantines), "quarantine_share": round(share, 4),
              "quarantine_cap": QUARANTINE_CAP, "per_family": by_fam,
              "provenance": provenance,
              "note": "labels dérivés des run-result.json (docker, node) par rules-v1 "
                      "uniquement ; y=1 ⟺ F2P vert ET (P2P vert OU P2P non déclarés), "
                      "précédent s12_pool.py gelé"}
    (out_dir / "genfam-label-report.json").write_text(json.dumps(report, indent=1) + "\n")
    return 0, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quota", default="q1")
    ap.add_argument("--campaign-dir", default=None,
                    help="répertoire campagne (défaut genfam-<quota>)")
    args = ap.parse_args()
    cdir = args.campaign_dir or f"genfam-{args.quota}"
    qdir = ROOT / "data" / "landing" / "act2-pilot" / cdir
    rc, rep = build(qdir)
    if rep.get("status") == "EMPTY":
        print(rep["note"])
    elif rep.get("status") == "REFUSED":
        print(f"REFUSÉ : quarantaine {rep['quarantine_share']:.1%} > "
              f"{QUARANTINE_CAP:.0%} — diagnostic requis, aucun label émis")
    else:
        print(f"labels: {rep['labels']} (y=1: {rep['y1']}, y=0: {rep['y0']}) | "
              f"quarantaine: {rep['quarantines']} "
              f"({rep['quarantine_share']:.1%} ≤ {QUARANTINE_CAP:.0%}) | "
              f"familles: {len(rep['per_family'])}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
