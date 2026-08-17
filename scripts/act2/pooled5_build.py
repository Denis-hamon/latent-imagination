#!/usr/bin/env python3
"""NIGHT-HARVEST-v1 — construction pooled5 = pooled4 (113) + lignes harvest
validées. Textes reconstruits pour l'embedding jina (protocole identique :
state = ticket_text[:1200] + F2P, diff = diff généré, goal = zéro).
Run: uv run python scripts/act2/pooled5_build.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
NH = PILOT / "night-harvest"


def main() -> int:
    rows4 = json.loads((PILOT / "coverage-ts-pooled4" / "coverage-ts-pooled4-rows.json").read_text())
    d4 = np.load(PILOT / "coverage-ts-pooled4" / "coverage-ts-pooled4-embed.npz")
    verified = {t["issue"]: t for t in json.loads((NH / "verified.json").read_text())}
    states, diffs, new_rows, seen = [], [], [], set()
    excl = set(json.loads((NH / "exclude.json").read_text())) if (NH / "exclude.json").is_file() else set()
    for line in (NH / "harvest-results.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("id") in excl or r.get("type") == "incident-note":
            continue
        if not r.get("applied") or not isinstance(r.get("y"), int):
            continue
        key = r["id"]
        if key in seen:
            continue
        seen.add(key)
        t = verified.get(r["issue"])
        if t is None:
            continue
        df = NH / "tickets" / f"t{r['issue']}" / f"d{r['draw']}.diff"
        if not df.is_file():
            continue
        states.append((t["ticket_text"] or "")[:1200] + "\n" + "; ".join(t["f2p"][:6]))
        diffs.append(df.read_text())
        new_rows.append({"task": f"real__{r['issue']}", "slot": r["id"],
                         "family": f"omniroute_real__{r['issue']}",
                         "campaign": "night-harvest-v1", "window": "night-harvest-v1",
                         "author": r.get("author"), "draw": r.get("draw"),
                         "y": r["y"], "goal_free": True})
    print(f"lignes harvest valables : {len(new_rows)} "
          f"(pos {sum(r['y'] for r in new_rows)} / neg {len(new_rows) - sum(r['y'] for r in new_rows)})")
    out = PILOT / "pooled5-texts"
    out.mkdir(exist_ok=True)
    with (out / "texts.jsonl").open("w") as fh:
        for s, d in zip(states, diffs):
            fh.write(json.dumps({"state": s, "diff": d}) + "\n")
    (out / "rows-new.json").write_text(json.dumps(new_rows, indent=1, ensure_ascii=False) + "\n")
    (out / "pooled4-base.json").write_text(json.dumps(
        {"rows": [{k: r.get(k) for k in ("task", "slot", "family", "campaign", "window", "author", "draw", "y", "goal_free")}
                  for r in rows4],
         "note": "base pooled4 113 lignes ; embeds npz déjà dans coverage-ts-pooled4"}, indent=1) + "\n")
    print(f"-> {out}/texts.jsonl ({len(diffs)} textes à embedder jina sur node)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
