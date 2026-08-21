#!/usr/bin/env python3
"""v44 — grounding sweep périodique : une session produit par invocation,
rotation sur le stock vérifié, plafond 20 appels/jour.
Run: uv run python scripts/futures/grounding_sweep.py
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MSWB = ROOT / "data" / "landing" / "act2-pilot" / "mswb"
NH = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest"
COUNTER = NH / "sweep-counter-v44.jsonl"
DAILY_CAP = 20


def today_used() -> int:
    d = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    n = 0
    if COUNTER.is_file():
        for l in COUNTER.read_text().splitlines():
            if l.strip() and json.loads(l).get("date") == d:
                n += int(json.loads(l).get("calls", 0))
    return n


def queue() -> list[tuple[str, dict]]:
    out = []
    for repo in ("vuejs__core", "iamkun__dayjs"):
        f = MSWB / repo / "verified-mswb.json"
        if not f.is_file():
            continue
        for t in json.loads(f.read_text()):
            if t.get("ok"):
                out.append((repo, t))
    played = {p.name.replace("product-session-", "").replace(".json", "")
              for p in MSWB.glob("product-session-*.json")}
    done = {p.name.replace("product-session-resolved-", "").replace(".json", "")
            for p in MSWB.glob("product-session-resolved-*.json")}
    out = [(r, t) for (r, t) in out if t["issue"] not in done]
    out.sort(key=lambda x: (x[1]["issue"] in played, len(x[1]["f2p"])), reverse=False)
    return out


def main() -> int:
    used = today_used()
    if used >= DAILY_CAP:
        print(f"SWEEP SKIP : plafond journalier atteint ({used}/{DAILY_CAP})")
        return 0
    q = queue()
    if not q:
        print("SWEEP SKIP : file vide")
        return 0
    repo, t = q[0]
    print(f"SWEEP : {t['issue']} ({repo}) | budget restant {DAILY_CAP - used}")
    env = {"LI_MAX_TOKENS": "65536"}
    import os
    full_env = {**os.environ, **env}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "futures" / "product_session.py"),
                        "--ticket", t["issue"], "--max-turns", "3"],
                       capture_output=True, text=True, timeout=3600, env=full_env, check=False)
    print(r.stdout[-500:])
    calls = 0
    sess = MSWB / f"product-session-{t['issue']}.json"
    resolved = False
    if sess.is_file():
        d = json.loads(sess.read_text())
        calls = sum(1 for e in d.get("log", []) if e.get("reply_len") or e.get("diff_extrait"))
        resolved = d.get("résolu", False)
    if resolved:
        (MSWB / f"product-session-resolved-{t['issue']}.json").write_text(json.dumps(d, indent=1))
    with COUNTER.open("a") as fh:
        fh.write(json.dumps({"date": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"),
                             "ticket": t["issue"], "calls": calls, "resolved": resolved,
                             "window": "v44"}) + "\n")
    print(f"SWEEP OK : {calls} appels, résolu={resolved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
