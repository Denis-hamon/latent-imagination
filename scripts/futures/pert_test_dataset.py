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
    # (d) replay v22/v25 : paires réelles multi-repos (diffs sur disque)
    for vtag, vfile in (("v22", "v22-pairs.json"), ("v25", "v25-pairs.json"), ("v28", "v28-pairs.json")):
        vf = PILOT / "ts-gold-v18" / vfile
        if not vf.is_file():
            continue
        for r in json.loads(vf.read_text()):
            rows.append({"key": r["key"], "task": r["task"],
                         "declared_f2p": r["declared_f2p"], "red_set": r["red_set"],
                         "applied": "git", "source": f"{vtag}-replay",
                         "window": vtag, "model": r["model"], "turn": r["turn"]})
    # récupération declared_f2p (harvest : issue dans la clé ; legacy : staging)
    verifs = []
    for f in list((PILOT / "night-harvest").glob("*/verified.json")) + [PILOT / "night-harvest" / "verified.json"]:
        if f.is_file():
            verifs += json.loads(f.read_text())
    stag_tasks = {}
    for camp in sorted(PILOT.glob("coverage-ts-*")) + sorted(PILOT.glob("ts-v*")):
        se = camp / "staging-extract.json"
        if se.is_file():
            for t in json.loads(se.read_text())["tasks"]:
                stag_tasks[t["instance_id"].replace("/", "_")] = sorted(t.get("f2p", []))
    for r in rows:
        if r["declared_f2p"] or not r["red_set"]:
            continue
        k = r["key"]
        if r["source"] == "harvest-full" and "-d" in k:
            hrow = None
            for hf in sorted((PILOT / "night-harvest").glob("harvest-results*.jsonl")):
                for l in hf.read_text().splitlines():
                    if '"id"' in l and json.loads(l).get("id") == k:
                        hrow = json.loads(l)
                        break
                if hrow:
                    break
            if hrow:
                tv = next((t for t in verifs if t.get("issue") == hrow.get("issue")), None)
                if tv and tv.get("f2p"):
                    r["declared_f2p"] = sorted(tv["f2p"])
                    continue
            core = k.rsplit("-d", 1)[0]
            for t in verifs:
                iss = t.get("issue", "")
                tail = iss.rsplit("_", 1)[-1] if "_" in iss else iss
                if tail and (tail.lower().replace("_", "-") in core.lower()
                             or core.lower().endswith(iss.lower()[-24:].replace("_", "-"))):
                    r["declared_f2p"] = sorted(t.get("f2p", []))
                    break
        elif not r["declared_f2p"]:
            cand = r["task"].split("__", 1)[-1].replace("/", "_")
            for iid, f2p in stag_tasks.items():
                if f2p and (iid.endswith(cand[-40:]) or cand.endswith(iid.split("__")[-1][-40:])):
                    r["declared_f2p"] = f2p
                    break
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
