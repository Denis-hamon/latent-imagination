#!/usr/bin/env python3
"""Eval public falsifiable de latent-gate — AUCUNE dépendance interne.

Principe (falsifiabilité sans fuite) : pour chaque candidat, le service est
appelé avec exclude_task=<tâche du candidat> → le serveur retire TOUT le pool
de cette tâche avant de scorer. La courbe produite ici est donc une mesure
hors-échantillon par construction (leave-one-task-out). Sans --no-exclude,
toute dérive est affichée comme in-sample.

Usage :
  python run_eval.py --base-url http://localhost:8080 --api-key $KEY
Recalcule côté client : accuracy par couverture + IC95 de Wilson, et compare
à claims.json si présent.
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path

COVERAGES = (1.0, 0.75, 0.5, 0.4, 0.3, 0.25, 0.2, 0.1)


def wilson(k, n):
    z = 1.96
    p = k / max(1, n)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return max(0.0, c - h), min(1.0, c + h)


def call(base, key, tool, payload):
    req = urllib.request.Request(
        f"{base}/v1/{tool}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 **({"X-API-Key": key} if key else {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8080")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--pack", default=str(Path(__file__).parent / "eval-tasks.jsonl"))
    ap.add_argument("--no-exclude", action="store_true",
                    help="in-sample (affiché comme tel)")
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.pack).read_text().splitlines() if l.strip()]
    recs = []
    for t in rows:
        for c in t["candidates"]:
            payload = {"state_text": t["state"], "diff_text": c["diff"],
                       "goal_text": t["goal"]}
            if not args.no_exclude:
                payload["exclude_task"] = t["task"]
            out = call(args.base_url, args.api_key, "score_patch", payload)
            recs.append({"y": c["y"], "p": out.get("p_pass"),
                         "conf": out.get("confidence")})
    scored = [r for r in recs if r["p"] is not None]
    n = len(scored)
    y = [r["y"] for r in scored]
    maj = max(sum(y) / n, 1 - sum(y) / n)
    mode = "IN-SAMPLE — à lire comme témoin de pipeline, PAS comme mesure" \
        if args.no_exclude else "LOAO (exclude_task) — mesure hors-échantillon"
    print(f"\n== eval latent-gate : n={n} candidats, {len(rows)} tâches, "
          f"majorité {maj:.3f} | {mode} ==")
    order = sorted(range(n), key=lambda i: -scored[i]["conf"])
    print(f"{'couverture':>10} {'n':>4} {'acc':>7} {'IC95':>16}")
    for cov in COVERAGES:
        m = max(1, round(n * cov))
        sel = order[:m]
        k = sum(1 for i in sel
                if (scored[i]["p"] > 0.5) == bool(scored[i]["y"]))
        lo, hi = wilson(k, m)
        print(f"{cov:>10.0%} {m:>4} {k/m:>7.3f}   [{lo:.3f},{hi:.3f}]")

    claims = Path(__file__).parent / "claims.json"
    if claims.is_file():
        c = json.loads(claims.read_text())
        print(f"\nclaims publiés (model sha {c.get('model_sha256', '?')[:16]}) :")
        print(json.dumps(c.get("headline", {}), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
