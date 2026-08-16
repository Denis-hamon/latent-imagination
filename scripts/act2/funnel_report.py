#!/usr/bin/env python3
"""Story 12.4 — funnel de conversion scan → grounded outcome → pool row (NFR-K1).

LE KPI produit : taux de conversion du flywheel. Re-dérivable des logs bruts
(mcp-log.jsonl) + artefacts de collecte (candidates.json, flywheel-rows.json) :
aucun chiffre n'est copié d'un rapport antérieur. Strates = reporter du scan
(l'appariement outcome↔scan se fait par call_id, comme mcp_flywheel collect).

Étages :
  1 scans           : entrées risk_scan avec capture (diff_sha + state_sha)
  2 outcomes        : report_outcome GROUNDÉS (grounded_by non vide ; les non-
                      groundés sont REJETÉS — jamais comptés comme conversions)
  3 pairs           : paires promouvables (collect : appariement call_id +
                      label gate + dédup, candidats dans candidates.json)
  4 rows            : lignes goal_free assemblées prêtes à embed (flywheel-rows)

Taux par strate : r_report = outcomes/scans, label-gate survival = pairs/
outcomes appariés, dedup = pairs/candidats-bruts si mesurable, end-to-end =
rows/scans. Strate vide ⇒ None (honest emptiness, jamais 0.0 inventé).

Sortie : governance/act2/arm-artifacts/funnel-mcp-flywheel-1.json
Run: uv run python scripts/act2/funnel_report.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
LOG = PILOT / "mcp-log.jsonl"
FLY = PILOT / "mcp-flywheel"
OUT = ROOT / "governance" / "act2" / "arm-artifacts" / "funnel-mcp-flywheel-1.json"


def _rate(num: int | None, den: int | None):
    if num is None or not den:
        return None  # strate vide ⇒ None, jamais 0.0 (honest emptiness)
    return round(num / den, 4)


def main() -> int:
    rows = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]
    scans = [r for r in rows if r.get("type") == "risk_scan"
             and r.get("diff_sha") and r.get("state_sha")]
    outcomes = [r for r in rows if r.get("type") in ("outcome", "report_outcome")]
    grounded = [o for o in outcomes if o.get("grounded_by")]
    rejected_non_grounded = len(outcomes) - len(grounded)

    by_call = {r.get("call_id"): r for r in scans if r.get("call_id")}
    matched_outcomes = [o for o in grounded if o.get("call_id") in by_call]

    candidates = json.loads((FLY / "candidates.json").read_text())
    fw_rows = json.loads((FLY / "flywheel-rows.json").read_text())

    # strate par reporter du SCAN apparié
    strata = defaultdict(lambda: {"scans": 0, "outcomes": 0, "pairs": 0})
    for s in scans:
        strata[s.get("reporter") or "none"]["scans"] += 1
    for o in matched_outcomes:
        rep = by_call[o["call_id"]].get("reporter") or "none"
        strata[rep]["outcomes"] += 1
    for c in candidates:
        rep = by_call.get(c.get("call_id"), {}).get("reporter") or "none"
        strata[rep]["pairs"] += 1

    strat_out = {}
    for rep, st in sorted(strata.items()):
        strat_out[rep] = {
            **st,
            "rows": sum(1 for r in fw_rows if r.get("provenance", {}).get("reporter") == rep)
            if rep != "none" else None,
            "r_report": _rate(st["outcomes"], st["scans"]),
            "label_gate_survival": _rate(st["pairs"], st["outcomes"]),
            "end_to_end_rows_per_scan": _rate(st["pairs"], st["scans"]),
        }

    global_rates = {
        "scans_with_capture": len(scans),
        "outcomes_total": len(outcomes),
        "outcomes_grounded": len(grounded),
        "outcomes_non_groundés_rejetés": rejected_non_grounded,
        "outcomes_appariés": len(matched_outcomes),
        "pairs_promouvables": len(candidates),
        "rows_goal_free": len(fw_rows),
        "r_report": _rate(len(grounded), len(scans)),
        "appariement": _rate(len(matched_outcomes), len(grounded)),
        "label_gate_survival": _rate(len(candidates), len(matched_outcomes)),
        "end_to_end_rows_per_scan": _rate(len(fw_rows), len(scans)),
        "baseline_epics_reference": 0.22,
    }

    report = {
        "story": "12.4-conversion-funnel",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "kpi": "end_to_end_rows_per_scan — LE taux qui gouverne la masse critique",
        "rederivable_from": [str(LOG.relative_to(ROOT)),
                             str((FLY / "candidates.json").relative_to(ROOT)),
                             str((FLY / "flywheel-rows.json").relative_to(ROOT))],
        "global": global_rates,
        "per_reporter_strata": strat_out,
        "publish_with": "chaque promotion pool publie ce funnel mis à jour (AC 12.4)",
        "note": "les outcomes non groundés sont rejetés du numérateur (pas de "
                "conversion par opinion) ; strates vides ⇒ None",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"funnel global : {len(scans)} scans → {len(grounded)} outcomes groundés "
          f"({rejected_non_grounded} non-groundés rejetés) → {len(candidates)} paires "
          f"→ {len(fw_rows)} rows | end-to-end = {global_rates['end_to_end_rows_per_scan']} "
          f"(réf baseline epics 0.22)")
    print(f"→ {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
