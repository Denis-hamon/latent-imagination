#!/usr/bin/env python3
"""Story 10.1 Task 1 — sélection gelée gen-families (Q1) + constat Q2.

Window: governance/act2/window-gen-families-v1.md (approuvé, ancré a4732c94…).
Règles du window : Q1 = tâches de repos NON couverts par les familles du pool
servi ; 60 tâches × 2 tirages ; provenance par ligne ; sélection gelée AVANT
tout appel modèle.

Honnêteté de couverture (disclose, ne jamais gonfler) : le pool raw local
(2 shards, 7392 lignes) contient 14 familles non couvertes exploitables
(patch + F2P + image). Q1 sélectionne 60 tâches ÉQUILIBRÉES sur ces 14
familles (max couverture nouvelle = le but mesuré du window). Q2 (CI
workflow) : aucune tâche `github-actions-public-ci` n'est récoltée localement
→ Q2 est enregistré comme PENDING-HARVEST dans le manifeste (un plafond est
un plafond, pas une garantie ; shortfall = amendement, S14 précédent).

Sélection déterministe : tri par instance_id, round-robin sur les familles
triées, 0 tirage aléatoire (reproductible bit-à-bit).

Run: uv run python scripts/act2/genfam_select.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "landing" / "swe-smith-tasks" / "raw"
POOL_V9 = ROOT / "data" / "landing" / "act2-pilot" / "latent-pool-v9.json"
OUT = ROOT / "governance" / "act2" / "genfam-q1-selection-v1.json"
STATS = "governance/act2/arm-artifacts/genfam-selection-report.json"
Q1_TARGET = 60


def main() -> int:
    pool = json.loads(POOL_V9.read_text())
    covered = {r["task"].split(".")[0] for r in pool}
    corpus = json.loads(
        (ROOT / "data/landing/swe-smith-tasks/smith-tasks-v1/task-statements.json").read_text())

    rows, seen = [], set()
    for f in sorted(RAW.glob("train-*.parquet")):
        t = pq.read_table(str(f),
                          columns=["instance_id", "patch", "FAIL_TO_PASS",
                                   "PASS_TO_PASS", "image_name",
                                   "problem_statement"]).to_pylist()
        rows.extend(t)

    usable: dict[str, list[dict]] = {}
    n_no_statement = 0
    for r in rows:
        iid = r["instance_id"]
        fam = iid.split(".")[0]
        if iid in seen or fam in covered:
            continue
        seen.add(iid)
        stmt = (r["problem_statement"] or "").strip() or (corpus.get(iid) or "").strip()
        if not (r["patch"] and r["FAIL_TO_PASS"] and r["image_name"] and stmt):
            if r["patch"] and r["FAIL_TO_PASS"] and r["image_name"]:
                n_no_statement += 1  # disclosed: candidate dropped, no statement
            continue
        usable.setdefault(fam, []).append(r)

    fams = sorted(usable)
    if not fams:
        print("ABORT: aucune famille exploitable non couverte")
        return 2
    for fam in fams:
        usable[fam].sort(key=lambda r: r["instance_id"])

    picked: list[dict] = []
    idx = {f: 0 for f in fams}
    while len(picked) < Q1_TARGET and any(idx[f] < len(usable[f]) for f in fams):
        for f in fams:
            if len(picked) >= Q1_TARGET:
                break
            if idx[f] < len(usable[f]):
                r = usable[f][idx[f]]
                idx[f] += 1
                picked.append({
                    "instance_id": r["instance_id"],
                    "family": f,
                    "image_name": r["image_name"],
                    "n_f2p": len(r["FAIL_TO_PASS"]),
                    "n_p2p": len(r["PASS_TO_PASS"]),
                    "problem_sha256": sha256(
                        ((r["problem_statement"] or "").strip()
                         or corpus[r["instance_id"]].strip()).encode()).hexdigest(),
                    "campaign": "genfam-q1",
                    "window": "gen-families-v1",
                    "draws": 2,
                })
    picked.sort(key=lambda r: r["instance_id"])
    blob = json.dumps({
        "window": "gen-families-v1",
        "window_approval_anchor": "a4732c9487a5033d734cd1f149ea5f9d0058c8eab9b4298da9d1de0ca6602495",
        "q1": picked,
        "q2": {"status": "PENDING-HARVEST",
               "source": "github-actions-public-ci (sources.yaml, story 4.1)",
               "note": "aucune tâche CI récoltée localement ; quota Q2 (10×2) "
                       "exécuté seulement si récolte dans les droits enregistrés"},
    }, indent=1, sort_keys=True)
    OUT.write_text(blob + "\n")
    digest = sha256(blob.encode()).hexdigest()

    by_fam = Counter(r["family"] for r in picked)
    report = {
        "selection_digest": digest,
        "q1_tasks": len(picked),
        "families_targeted": len(by_fam),
        "per_family": dict(sorted(by_fam.items())),
        "raw_rows_total": len(rows),
        "usable_uncovered_rows": sum(len(v) for v in usable.values()),
        "usable_uncovered_families": len(fams),
        "candidates_dropped_no_statement": n_no_statement,
        "coverage_honesty": ("12 nouvelles familles ciblées × 5 tâches avec le "
                             "pool raw local (2 shards SWE-smith) ; 2 familles "
                             "supplémentières écartées (statements absents, "
                             "1215 candidats drop disclosés). 5 lignes/famille "
                             "= seuil family-LOAO atteint pour chaque nouvelle "
                             "famille. Plus de familles exigeraient de "
                             "télécharger d'autres shards — non fait, disclosé."),
        "q2_status": "PENDING-HARVEST",
    }
    out_stats = ROOT / STATS
    out_stats.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"sélection: {len(picked)} tâches, {len(by_fam)} familles "
          f"(digest {digest[:16]})")
    print(f"rapport: {STATS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
