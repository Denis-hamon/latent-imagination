#!/usr/bin/env python3
"""v27 — convertisseur Multi-SWE-bench (CC0) -> tickets vérifiables.

Chaque instance devient un ticket au format verified.json avec :
- parent = base.sha, gold = fix_patch (texte), test_patch séparé ;
- f2p = noms leaf des tests marqués test:FAIL/fix:PASS ;
- tests_run = fichiers de test_patch ∪ fichiers des f2p ;
- src_files = fichiers du fix_patch.
La vérification RED->GREEN se fera par application des patchs (pas de git
commit requis) — script verify dédié v27.
Run: uv run python scripts/act2/mswb_convert.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path("/home/ubuntu/multi-swe-bench")  # rempli via ssh après
OUT = ROOT / "data" / "landing" / "act2-pilot" / "mswb"

HUNK_FILE = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.M)


def files_of_patch(patch: str) -> list[str]:
    seen = []
    for m in HUNK_FILE.finditer(patch or ""):
        if m.group(2) not in seen:
            seen.append(m.group(2))
    return seen


def leaf(name: str) -> str:
    return name.split(" > ")[-1].strip()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    total, out_rows, per_repo = 0, [], {}
    for f in sorted(SRC.glob("*_dataset.jsonl")) if SRC.is_dir() else []:
        pass
    import sys
    for path in sys.argv[1:]:
        f = Path(path)
        repo_key = f.name.replace("_dataset.jsonl", "")
        n = 0
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            total += 1
            f2p_full = d.get("f2p_tests") or {}
            if isinstance(f2p_full, dict):
                f2p = sorted({leaf(k) for k, v in f2p_full.items()
                              if v.get("test") == "FAIL" and v.get("fix") == "PASS"})
            else:
                continue
            test_files = files_of_patch(d.get("test_patch", ""))
            f2p_files = sorted({k.split(" > ")[0] for k in f2p_full}) if isinstance(f2p_full, dict) else []
            tests_run = sorted(set(test_files + f2p_files))
            if not f2p or not tests_run:
                continue
            out_rows.append({
                "issue": d["instance_id"], "repo": repo_key, "org": d["org"],
                "parent": d["base"]["sha"], "fix_patch": d.get("fix_patch", ""),
                "test_patch": d.get("test_patch", ""),
                "src_files": files_of_patch(d.get("fix_patch", "")),
                "tests_run": tests_run, "f2p": f2p,
                "p2p_n": len(d.get("p2p_tests") or {}),
                "ticket_text": (d.get("title", "") + "\n" + (d.get("body") or ""))[:1400],
                "mswb_fix_result": str(d.get("fix_patch_result"))[:200],
            })
            n += 1
        per_repo[repo_key] = n
    (OUT / "mswb-tickets.json").write_text(json.dumps(out_rows, indent=1, ensure_ascii=False) + "\n")
    print(f"instances lues : {total} | tickets convertis : {len(out_rows)}")
    print("par repo :", json.dumps(per_repo, indent=1))
    n_small = sum(1 for r in out_rows
                  if r["fix_patch"].count("\n") + r["test_patch"].count("\n") < 200)
    print(f"patchs compacts (<200 lignes combinées) : {n_small}/{len(out_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
