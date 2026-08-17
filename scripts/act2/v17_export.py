#!/usr/bin/env python3
"""Fenêtre v17 (7072deb9) — export goal TS : lignes harvest appliquées dont le
ticket porte fix_commit. State/diff bit-identiques au disque ; gold = diff du
vrai fix (git show fix_commit au parent). Zéro génération.

Run: uv run python scripts/act2/v17_export.py
"""
from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NH = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest"
OUT = ROOT / "data" / "landing" / "act2-pilot" / "ts-gold-v18"

REPOS = {"omniroute": "~/OmniRoute", "zod": "~/zod-source", "date-fns": "~/date-fns-source"}


def sh_remote(cmd: str) -> str:
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=12", "Kimsufi-standard", cmd],
                       capture_output=True, text=True, timeout=120, check=False)
    return r.stdout


def main() -> int:
    OUT.mkdir(exist_ok=True)
    verified = {}
    for f in list(NH.glob("*/verified.json")) + [NH / "verified.json"]:
        for t in json.loads(f.read_text()):
            repo = f.parent.name if f.parent != NH else "omniroute"
            t.setdefault("repo", repo)
            verified[t["issue"]] = t
    # index tickets-dir par prompt_sha256
    prompts = {}
    for d in sorted(NH.glob("tickets/*")):
        pt = d / "prompt.txt"
        if pt.is_file():
            prompts[sha256(pt.read_text().encode()).hexdigest()[:16]] = d
    rows = []
    for jf in sorted(NH.glob("harvest-results*.jsonl")):
        for l in jf.read_text().splitlines():
            if '"issue"' not in l:
                continue
            r = json.loads(l)
            if not r.get("applied"):
                continue
            t = verified.get(r["issue"])
            if not t or not t.get("fix_commit"):
                continue
            tdir = prompts.get(r.get("prompt_sha256"))
            n = str(r.get("draw"))
            if not tdir or not (tdir / f"d{n}.diff").is_file():
                continue
            state = (t.get("ticket_text") or "")[:1200] + "\n" + "; ".join(map(str, t["f2p"][:6]))
            rows.append({
                "key": r["id"], "task": f"{t['repo']}__{t['issue']}", "repo": t["repo"],
                "y": int(r["y"]), "state": state,
                "diff": (tdir / f"d{n}.diff").read_text(),
                "fix_commit": t["fix_commit"], "src_files": t["src_files"],
                "parent": t.get("parent"), "window": r.get("window")})
    uniq = {}
    for r in rows:
        gk = (r["repo"], r["fix_commit"], tuple(sorted(r["src_files"])))
        uniq[gk] = r["key"]
    print(f"lignes exportables : {len(rows)} | golds uniques : {len(uniq)}")
    golds = {}
    for (repo, fix, srcs) in uniq:
        remote = REPOS.get(repo)
        if not remote:
            continue
        base = fix + "~1"
        cmd = f"cd {remote} && git diff {base} {fix} -- {' '.join(srcs)}"
        g = sh_remote(cmd)
        if g.strip():
            golds[(repo, fix, tuple(sorted(srcs)))] = g
    ok = 0
    for r in rows:
        gk = (r["repo"], r["fix_commit"], tuple(sorted(r["src_files"])))
        r["gold"] = golds.get(gk, "")
        ok += bool(r["gold"])
    rows = [r for r in rows if r["gold"]]
    (OUT / "v18-rows.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    y1 = sum(r["y"] for r in rows)
    print(f"-> v18-rows.json : {len(rows)} lignes ({y1}+ / {len(rows) - y1}-), golds présents {ok}, repos {set(x[chr(39)+"repo"+chr(39)] if False else x["repo"] for x in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
