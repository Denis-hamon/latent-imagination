#!/usr/bin/env python3
"""MCP flywheel — stage 1 : collecte des paires groundées depuis mcp-log.jsonl.

Le MCP (ghost_server (GHOST MCP) v0.3+) journalise chaque risk_scan (state, diff,
reporter=LLM auteur, score, décision) et chaque report_outcome (call_id,
passed, reporter, grounded_by). Ce script apparie les deux et produit le
matériau du renforcement du world model :

  1. join outcome ↔ risk_scan par call_id ;
  2. filtre : issue GROUNDÉE seulement (grounded_by renseigné — leçon S11/S13 :
     jamais de label auto-déclaré par le LLM) ;
  3. dédup : par diff_sha contre le batch ET contre les diffs du pool courant
     (les régénérations identiques n'apportent rien — mesuré en S12 : 16/23) ;
  4. stratification par reporter (auteur) : n, taux de positifs, taux d'abstention
     du serveur sur ses diffs — alerte poison si un auteur s'écarte trop de la
     base (leçon S11 : auteur hétérogène = risque de géométrie empoisonnée).

Sorties : mcp-flywheel/candidates.json (les paires prêtes à embed/promouvoir)
        + mcp-flywheel/collect-report.json. Zéro embed, zéro promotion : la
géométrie v9 et l'entrée au pool restent des étapes distinctes, à la main de
l'owner (comme les pools v6/v7/v8).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
LOG = Path(sys.argv[1]) if len(sys.argv) > 1 else PILOT / "mcp-log.jsonl"
OUT = PILOT / "mcp-flywheel"
POOL_JSON = PILOT / "latent-pool-v8.json"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not LOG.is_file():
        print("mcp-log.jsonl absent — aucun trafic MCP encore.")
        return 0
    scans: dict[str, dict] = {}
    outcomes: dict[str, dict] = {}
    n_other = 0
    for ln in LOG.read_text().splitlines():
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if e.get("type") == "risk_scan" and e.get("state_text"):
            scans[e["call_id"]] = e
        elif e.get("type") == "outcome":
            outcomes[e["call_id"]] = e
        else:
            n_other += 1

    pool = json.loads(POOL_JSON.read_text()) if POOL_JSON.is_file() else []
    known_diffs = {sha256(r["diff"].strip().encode()).hexdigest() for r in pool}
    pos_rate_pool = sum(r["y"] for r in pool) / max(1, len(pool))

    pairs, seen = [], set()
    stats = defaultdict(lambda: {"n": 0, "pos": 0, "abstained": 0, "dups": 0})
    ungrounded = unmatched = 0
    for cid, o in outcomes.items():
        s = scans.get(cid)
        if not s:
            unmatched += 1
            continue
        rep = o.get("reporter") or s.get("reporter") or "unknown"
        st = stats[rep]
        st["n"] += 1
        if not o.get("grounded_by"):
            ungrounded += 1
            continue  # leçon S11 : pas de label auto-déclaré dans le pool
        h = s.get("diff_sha") or sha256(s["diff_text"].strip().encode()).hexdigest()
        st["pos"] += int(bool(o["passed"]))
        st["abstained"] += int(s.get("decision") == "abstain")
        if h in known_diffs or h in seen:
            st["dups"] += 1
            continue
        seen.add(h)
        pairs.append({
            "call_id": cid, "reporter": rep,
            "grounded_by": o["grounded_by"], "passed": bool(o["passed"]),
            "state_text": s["state_text"], "diff_text": s["diff_text"],
            "state_sha": s.get("state_sha"), "diff_sha": h,
            "server_decision": s.get("decision"),
            "server_confidence": s.get("confidence"),
            "exclude_task": s.get("exclude_task"),
            "collected_at": o["ts"],
        })

    alerts = []
    for rep, st in stats.items():
        if st["n"] >= 10:
            pr = st["pos"] / st["n"]
            if abs(pr - pos_rate_pool) > 0.35:
                alerts.append(f"auteur {rep}: taux positifs {pr:.0%} vs base pool "
                              f"{pos_rate_pool:.0%} — vérif distribution avant merge "
                              f"(leçon S11)")
    report = {
        "log": str(LOG),
        "risk_scan_avec_capture": len(scans),
        "outcomes": len(outcomes),
        "outcomes_non_appariés": unmatched,
        "outcomes_non_groundés_rejetés": ungrounded,
        "paires_promouvables": len(pairs),
        "pool_courant": {"lignes": len(pool), "taux_positifs": round(pos_rate_pool, 3)},
        "par_auteur": {k: dict(v) for k, v in sorted(stats.items())},
        "alertes_poison": alerts,
        "autres_entrées_log": n_other,
    }
    (OUT / "candidates.json").write_text(json.dumps(pairs, indent=1))
    (OUT / "collect-report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    print(f"\n→ {OUT / 'candidates.json'} ({len(pairs)} paires prêtes pour "
          f"embed/promotion — étape suivante à la main de l'owner)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
