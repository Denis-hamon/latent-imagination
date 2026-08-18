#!/usr/bin/env python3
"""v15 — assemblage du dataset per-test : lignes {patch, red-set nommée}.

Sources :
 (a) campagnes v15 avec outcomes_after complet (labeler ts_v15) ;
 (b) harvest v15-B (failed_all/passed_all post-patch) ;
 (c) audit P2.0 legacy : red-sets reconstruits depuis les tails (plus faible).
Population d'intérêt : réparations PARTIELLES (red_set non vide).
Run: uv run python scripts/futures/pert_test_dataset.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
NH = PILOT / "night-harvest"
OUT = PILOT / "pert-test-dataset"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    rows = []
    # (a) campagnes v15 labelées : red-set extrait des tails texte complets
    def parse_tail(tail: str) -> set:
        return {l.strip()[len("failed: "):] for l in tail.splitlines()
                if l.strip().startswith("failed: ")}
    for camp in ("coverage-ts-15a-flash", "coverage-ts-15a-qwen"):
        staging = json.loads((PILOT / camp / "staging-extract.json").read_text())
        stag_by = {t["instance_id"]: t for t in staging["tasks"]}
        for f in sorted((PILOT / camp / "gen-results").glob("*/run-result.json")):
            r = json.loads(f.read_text())
            if not r.get("patch_applied") or not isinstance(r.get("f2p_rc"), int):
                continue
            task = stag_by.get(r["task"])
            tail = (r.get("f2p_tail") or "") + "\n" + (r.get("p2p_tail") or "")
            red = sorted(parse_tail(tail))
            rows.append({"key": f"{camp}/{r['slot']}", "task": r["task"],
                         "declared_f2p": sorted(task["f2p"]) if task else [],
                         "red_set": red, "applied": r.get("apply_mode"),
                         "source": "v15-label", "window": "v15"})
    # (b) harvest v15-B et lignes avec outcomes complets
    leg = NH / "harvest-results-v13.jsonl"
    if leg.is_file():
        for l in leg.read_text().splitlines():
            if '"issue"' not in l:
                continue
            r = json.loads(l)
            if not r.get("applied") or "failed_all" not in r:
                continue
            red = sorted(r.get("failed_all", []))
            rows.append({"key": r["id"], "task": f"real__{r['issue']}",
                         "declared_f2p": [], "red_set": red,
                         "applied": r.get("apply_mode"), "source": "harvest-full",
                         "window": r.get("window", "?")})
    # (c) legacy partiels (audit P2.0) — red-set seule
    legacy = ROOT / "governance/act2/arm-artifacts/p2-per-test-extract-2026-08-17.json"
    if legacy.is_file():
        for p in json.loads(legacy.read_text()):
            rows.append({"key": p["slot"], "task": p["task"], "declared_f2p": [],
                         "red_set": sorted(p["red"]), "applied": "?",
                         "source": "p2-legacy", "window": "pre-v15"})
    # (d) replay v22 : paires réelles multi-repos ( diffs sur disque )
    v22 = PILOT / "ts-gold-v18" / "v22-pairs.json"
    if v22.is_file():
        for r in json.loads(v22.read_text()):
            rows.append({"key": r["key"], "task": r["task"],
                         "declared_f2p": r["declared_f2p"], "red_set": r["red_set"],
                         "applied": "git", "source": "v22-replay",
                         "window": "v22", "model": r["model"], "turn": r["turn"]})
    # dédup keys
    seen, uniq = set(), []
    for r in rows:
        if r["key"] in seen:
            continue
        seen.add(r["key"])
        uniq.append(r)
    partial = [r for r in uniq if r["red_set"]]
    (OUT / "pert-test-rows.json").write_text(json.dumps(uniq, indent=1, ensure_ascii=False) + "\n")
    print(f"dataset per-test : {len(uniq)} lignes, dont {len(partial)} PARTIELLES (red non vide)")
    import collections
    src = collections.Counter(r["source"] for r in partial)
    print("partielles par source :", dict(src))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
