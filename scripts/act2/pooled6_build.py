#!/usr/bin/env python3
"""v13 — pooled6 = pooled5 (219) + lignes collecte v13 multi-repos.
Textes pour embed jina : state = ticket_text[:1200] + F2P ; diff = diff généré.
Run: uv run python scripts/act2/pooled6_build.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
NH = PILOT / "night-harvest"


def main() -> int:
    verified = {}
    for repo in ("omniroute", "zod", "date-fns"):
        f = NH / repo / "verified.json"
        if f.is_file():
            for t in json.loads(f.read_text()):
                verified[(repo, t["issue"])] = t
                verified.setdefault(t["issue"], t)
    legacy = NH / "verified.json"
    if legacy.is_file():
        for t in json.loads(legacy.read_text()):
            verified.setdefault(t["issue"], t)
    excl = set(json.loads((NH / "exclude.json").read_text())) if (NH / "exclude.json").is_file() else set()
    rows5 = json.loads((PILOT / "pooled5" / "pooled5-rows.json").read_text())
    states, diffs, new_rows, seen = [], [], [], set()
    f = NH / "harvest-results-v13.jsonl"
    if f.is_file():
        for line in f.read_text().splitlines():
            if not line.strip() or '"id"' not in line:
                continue
            r = json.loads(line)
            rid = r.get("id")
            if rid in seen or rid in excl or not r.get("applied") or not isinstance(r.get("y"), int):
                continue
            seen.add(rid)
            t = verified.get(r.get("issue")) or verified.get((r.get("repo", "omniroute"), r.get("issue")))
            if t is None:
                continue
            # diff stocké sous tickets/v13-<repo>-<hash>/d<draw>.diff — retrouver par id
            cand_dirs = list(NH.glob(f"tickets/v13-{r.get('repo', 'omniroute')}-*"))
            df = None
            for d in cand_dirs:
                p = d / f"d{r.get('draw')}.diff"
                pr = d / "prompt.txt"
                if p.is_file() and pr.is_file() and t.get("ticket_text", "")[:40] in pr.read_text()[:300]:
                    df = p
                    break
            if df is None:
                continue
            states.append((t.get("ticket_text") or "")[:1200] + "\n" + "; ".join(map(str, t["f2p"][:6])))
            diffs.append(df.read_text()[:6000])
            fam = {"omniroute": "omniroute__real", "zod": "zod__real", "date-fns": "date_fns__real"}.get(
                r.get("repo", "omniroute"), "ts__real")
            new_rows.append({"task": f"real13__{r['issue']}", "slot": rid, "family": fam,
                             "campaign": "coverage-ts-v13", "window": "coverage-ts-v13",
                             "author": r.get("author"), "draw": r.get("draw"),
                             "y": r["y"], "goal_free": True})
    out = PILOT / "pooled6-texts"
    out.mkdir(exist_ok=True)
    with (out / "texts.jsonl").open("w") as fh:
        for s, d in zip(states, diffs):
            fh.write(json.dumps({"state": s, "diff": d}) + "\n")
    (out / "rows-new.json").write_text(json.dumps(new_rows, indent=1, ensure_ascii=False) + "\n")
    import numpy as np
    z5 = np.load(PILOT / "pooled5" / "pooled5-embed.npz")
    print(f"pooled6 : base {len(rows5)} + {len(new_rows)} nouvelles lignes v13")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
