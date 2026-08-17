#!/usr/bin/env python3
"""v14 — pooled7 = pooled6 (546) + lignes v14 (date-fns flash/qwen labelisées +
continuation harvest-results-v13 post-6c5d6293 = zod v14).
DISCLOSURE comptable : le harness harvest écrit les récoltes v14-zod dans
harvest-results-v13.jsonl (fichier hérité) ; la coupure v14 = lignes
timestampées après l'ancrage 6c5d6293 (2026-08-17T~10:0x) ET window v13 non
encore comptées dans pooled6. DW-45 ouvert : paramétrer window/results par
fenêtre.
Run: uv run python scripts/act2/pooled7_build.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
NH = PILOT / "night-harvest"
V14_ANCHOR = "2026-08-17T09:00:00"  # ancrage v14 6c5d6293 ~10:0x locales ; coupure large


def main() -> int:
    rows6 = json.loads((PILOT / "pooled6" / "pooled6-rows.json").read_text())
    have = {r.get("slot") for r in rows6}
    states, diffs, new_rows = [], [], []
    # (a) campagnes date-fns v14 labelisées
    for cdir in ("coverage-ts-v14-df-flash", "coverage-ts-v14-df-qwen", "coverage-ts-v14-df2-flash"):
        camp = PILOT / cdir
        lab = camp / "labels" / "genfam-label-report.json"
        st = json.loads((camp / "staging-extract.json").read_text())
        stag_by = {t["instance_id"]: t for t in st["tasks"]}
        if not lab.is_file():
            continue
        rep = json.loads(lab.read_text())
        prov = {p["attempt_id"]: p for p in rep["provenance"] if p.get("layer") == "label"}
        for sd in sorted(camp.glob("gen-results/*-d*")):
            rr = sd / "run-result.json"
            dp = sd / "diff.patch"
            if not (rr.is_file() and dp.is_file()):
                continue
            r = json.loads(rr.read_text())
            slot = sd.name
            if slot in have or not r.get("patch_applied") or slot not in prov:
                continue
            y = prov[slot].get("y")
            if not isinstance(y, int):
                continue
            t = stag_by.get(r["task"])
            if t is None:
                continue
            states.append(t["problem"][:1200] + "\n" + "; ".join(map(str, t["f2p"][:6])))
            diffs.append(dp.read_text()[:6000])
            new_rows.append({"task": r["task"], "slot": slot,
                             "family": t["instance_id"].split(".")[0],
                             "campaign": cdir, "window": "coverage-ts-v14",
                             "author": (st.get("author") or "?"), "draw": r.get("draw"),
                             "y": y, "goal_free": True})
    # (b) harvest-results-v13.jsonl : lignes v14-zod (post-ancrage, non encore poolées)
    verified_zod = {t["issue"]: t for t in json.loads((NH / "zod" / "verified.json").read_text())}
    for line in (NH / "harvest-results-v13.jsonl").read_text().splitlines():
        if '"issue"' not in line:
            continue
        r = json.loads(line)
        ts = r.get("ts", "") if ("ts" in r) else ""
        if not r.get("applied") or not isinstance(r.get("y"), int):
            continue
        if r.get("repo") != "zod":
            continue
        rid = r["id"]
        if rid in have or ts < V14_ANCHOR:
            continue
        t = verified_zod.get(r["issue"])
        if t is None:
            continue
        df = None
        for d in NH.glob("tickets/v13-zod-*"):
            pr = d / "prompt.txt"
            p = d / f"d{r.get('draw')}.diff"
            if p.is_file() and pr.is_file() and t.get("ticket_text", "")[:30] in pr.read_text()[:300]:
                df = p
                break
        if df is None:
            continue
        have.add(rid)
        states.append((t.get("ticket_text") or "")[:1200] + "\n" + "; ".join(map(str, t["f2p"][:6])))
        diffs.append(df.read_text()[:6000])
        new_rows.append({"task": f"real14__{r['issue']}", "slot": rid, "family": "zod__real",
                         "campaign": "coverage-ts-v14", "window": "coverage-ts-v14",
                         "author": r.get("author"), "draw": r.get("draw"),
                         "y": r["y"], "goal_free": True})
    out = PILOT / "pooled7-texts"
    out.mkdir(exist_ok=True)
    with (out / "texts.jsonl").open("w") as fh:
        for s, d in zip(states, diffs):
            fh.write(json.dumps({"state": s, "diff": d}) + "\n")
    (out / "rows-new.json").write_text(json.dumps(new_rows, indent=1, ensure_ascii=False) + "\n")
    print(f"pooled7 : base {len(rows6)} + {len(new_rows)} nouvelles lignes v14")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
