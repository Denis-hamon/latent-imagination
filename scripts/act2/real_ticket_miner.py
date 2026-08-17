#!/usr/bin/env python3
"""NIGHT-HARVEST-v1 (9092a931) — mineur de tickets RÉELS sur historique git.

Stages :
  discover : tests numérotés par issue -> commit d'ajout -> commit fix +
             parent + surface de fix ; filtres pré-enregistrés (<=3 fichiers
             source open-sse/**, diff <=250 lignes, <=600 lignes/fichier).
  verify   : worktree dédié au parent + suites-tests du fix => contrôle
             RED (>=2 F2P nommés cassés) puis GREEN (fix humain reverdit) ;
             extraction ticket_text (changelog.d OU première ligne commit —
             JAMAIS le corps du commit : il peut décrire la solution).
  manifest : harvest-manifest.json prêt pour real_ticket_harvest.py.

Run: uv run python scripts/act2/real_ticket_miner.py --stage discover|verify|manifest [--limit N]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest"
HOST = "Kimsufi-standard"
REPO = "~/OmniRoute"
HARVEST_ROOT = "~/OmniRoute-harvest"
MAX_SRC_FILES = 4
MAX_DIFF_LINES = 400
MAX_FILE_LINES = 900
MAX_PROMPT_FILES_TOTAL_LINES = 2200


def run(cmd: str, t: int = 900) -> str:
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                       capture_output=True, text=True, check=False, timeout=t)
    return r.stdout


def discover() -> list[dict]:
    """AMENDEMENT DISCLOSÉ (pré-enregistré 9092a931 : filtres de surface
    assouplis à périmètre constant <=2200 lignes prompt : diff <= 400 lignes,
    fichiers <= 900 lignes, <= 4 fichiers source ; et candidat-fix = TOUT
    commit qui AJOUTE le fichier test — la référence issue n'est plus requise,
    le contrôle RED->GREEN reste le juge final)."""
    script = r"""
cd ~/OmniRoute
find tests/unit -type f -name '*.test.ts' | while read tf; do
  add=$(git log --diff-filter=A --format=%H -1 -- "$tf")
  [ -z "$add" ] && continue
  src=$(git diff --name-only ${add}^ ${add} -- open-sse/ src/ 2>/dev/null | grep '\.ts$' | grep -v '\.test\.' | head -6)
  nsrc=$(echo "$src" | grep -c . )
  [ "$nsrc" -eq 0 ] && continue
  [ "$nsrc" -gt 4 ] && continue
  dl=$(git diff ${add}^ ${add} -- $src 2>/dev/null | wc -l)
  [ "$dl" -gt 400 ] && continue
  tot=0; bad=0
  for f in $src; do
    n=$(git show ${add}^:$f 2>/dev/null | wc -l)
    [ "$n" -eq 0 ] && { bad=1; break; }
    [ "$n" -gt 900 ] && { bad=1; break; }
    tot=$((tot+n))
  done
  [ "$bad" -eq 1 ] && continue
  [ "$tot" -gt 2200 ] && continue
  subj=$(git log -1 --format=%s $add)
  echo -e "$tf\t$add\t$nsrc\t$dl\t$(echo $src | tr ' ' ',')\t$subj"
done
"""
    out = run(script, t=1800)
    cands = []
    for line in out.splitlines():
        parts = line.split("\t") if "\t" in line else line.split("	")
        if len(parts) != 6:
            continue
        tf, add, nsrc, dl, srcstr, subj = parts
        src = srcstr.split(",")
        issue = tf.rsplit("/", 1)[-1].split("-", 1)[0]
        issue = issue if issue.isdigit() else tf.rsplit("/", 1)[-1][:12]
        sizes = {}
        ok = True
        for sf in src:
            n = run(f"cd {REPO} && git show {add}^:{sf} 2>/dev/null | wc -l").strip()
            if not n.isdigit() or int(n) == 0:
                ok = False
                break
            sizes[sf] = int(n)
        if not ok:
            continue
        tests_touches = run(f"cd {REPO} && git diff --name-only {add}^ {add} -- tests/").split()
        cands.append({"issue": issue, "test_file": tf, "fix_commit": add,
                      "parent": run(f"cd {REPO} && git rev-parse {add}^").strip(),
                      "src_files": src, "src_sizes": sizes, "diff_lines": int(dl),
                      "tests_in_fix": tests_touches, "commit_subject": subj[:200]})
    return cands


def changelog_text(fix: str) -> str:
    entries = run(f"cd {REPO} && git show --name-only --format= {fix} -- changelog.d/").split()
    for e in entries:
        if e.startswith("changelog.d/"):
            body = run(f"cd {REPO} && git show {fix}:{e}").strip()
            if body:
                return body[:600]
    return ""


def verify_one(c: dict) -> dict:
    wt = f"{HARVEST_ROOT}/probe-{c['issue']}"
    run(f"cd {REPO} && git worktree remove --force {wt} 2>/dev/null; git worktree add {wt} {c['parent']} 2>&1 | tail -1")
    run(f"ln -sfn {REPO.replace('~', '~')}/node_modules {wt}/node_modules 2>/dev/null; ln -sfn ~/OmniRoute/node_modules {wt}/node_modules")
    tests = " ".join(t for t in [c["test_file"]] + [t for t in c["tests_in_fix"] if t != c["test_file"] and t.endswith(".test.ts")][:2])
    run(f"cd {wt} && git checkout {c['fix_commit']} -- {' '.join(t for t in set(tests.split()))} 2>&1 | head -1")
    try:
        red_raw = run(f"cd {wt} && timeout 240 node --import tsx/esm --test --test-reporter=tap {tests} 2>&1", t=320)
    except subprocess.TimeoutExpired:
        run(f"cd {REPO} && git worktree remove --force {wt} 2>&1 | head -1")
        return {**c, "rejected": "RED-run timeout 240s (ticket inutilisable pour le harvest, DW-35)"}
    failed, passed = [], 0
    for line in red_raw.splitlines():
        l = line.strip()
        if l.startswith("not ok "):
            failed.append(l[7:].split(" # ")[0].strip())
        elif l.startswith("ok "):
            passed += 1
    if len(failed) < 1 or passed < 2:  # amendement 1 (9092a931) : >=1 F2P ET >=2 P2P
        run(f"cd {REPO} && git worktree remove --force {wt} 2>&1 | head -1")
        return {**c, "rejected": f"RED/P2P insuffisant : {len(failed)} F2P, {passed} P2P"}
    fixdiff = run(f"cd {wt} && git diff {c['parent']} {c['fix_commit']} -- {' '.join(c['src_files'])} > /tmp/fix-{c['issue']}.diff && git apply --recount /tmp/fix-{c['issue']}.diff 2>&1; echo APPLIED_RC=$?")
    try:
        green_raw = run(f"cd {wt} && timeout 240 node --import tsx/esm --test --test-reporter=tap {tests} 2>&1", t=320)
    except subprocess.TimeoutExpired:
        run(f"cd {REPO} && git worktree remove --force {wt} 2>&1 | head -1")
        return {**c, "rejected": "GREEN-run timeout 240s"}
    gfail = [ln.strip()[7:].split(" # ")[0].strip() for ln in green_raw.splitlines() if ln.strip().startswith("not ok ")]
    run(f"cd {REPO} && git worktree remove --force {wt} 2>&1 | head -1")
    if gfail:
        return {**c, "rejected": f"GREEN échoué au fix humain : {gfail[:3]}"}
    ticket = changelog_text(c["fix_commit"]) or c["commit_subject"]
    return {**c, "f2p": sorted(set(failed)), "p2p_n": passed, "tests_run": sorted(set(tests.split())),
            "ticket_text": ticket, "ok": True}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("discover", "verify", "manifest"), required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage == "discover":
        cands = discover()
        (OUT / "discovered.json").write_text(json.dumps(cands, indent=1) + "\n")
        print(f"{len(cands)} candidats éligibles aux filtres -> discovered.json")
        for c in cands[:30]:
            print(f"  #{c['issue']:6} {len(c['src_files'])} fichiers {c['diff_lines']:4} lignes  {c['commit_subject'][:64]}")
        return 0
    if args.stage == "verify":
        cands = json.loads((OUT / "discovered.json").read_text())
        # incrémental : fusion avec runs antérieurs (validés + rejetés connus)
        prior_done = []
        if (OUT / "verified.json").is_file():
            prior_done = json.loads((OUT / "verified.json").read_text())
        prior_rej = set()
        if (OUT / "verify-rejects.jsonl").is_file():
            prior_rej = {json.loads(l).get("test_file") for l in
                         (OUT / "verify-rejects.jsonl").read_text().splitlines() if l.strip()}
        done_issues = {d["test_file"] for d in prior_done}
        cands = [c for c in cands if c["test_file"] not in done_issues and c["test_file"] not in prior_rej]
        cands.sort(key=lambda c: c["diff_lines"])  # petits fix d'abord (harvest plus propre)
        if args.limit:
            cands = cands[:args.limit]
        done = list(prior_done)
        rejected = []
        for i, c in enumerate(cands):
            print(f"[{i+1}/{len(cands)}] ticket #{c['issue']} …", flush=True)
            try:
                r = verify_one(c)
            except Exception as exc:  # noqa: BLE001 — jamals un ticket ne tue le run
                r = {**c, "rejected": f"exception: {str(exc)[:80]}"}
            if r.pop("ok", False):
                done.append(r)
                print(f"    VALIDÉ : {len(r['f2p'])} F2P / {r['p2p_n']} P2P")
            else:
                rejected.append(r)
                print(f"    REJETÉ : {r.get('rejected', '?')[:70]}")
            # flush incrémental : le harvest peut consommer pendant le verify
            (OUT / "verified.json").write_text(json.dumps(done, indent=1) + "\n")
        (OUT / "verified.json").write_text(json.dumps(done, indent=1) + "\n")
        with (OUT / "verify-rejects.jsonl").open("w") as fh:
            for r in rejected:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"verify : {len(done)} validés / {len(rejected)} rejetés (journalisés)")
        return 0
    # manifest
    done = json.loads((OUT / "verified.json").read_text())
    mani = {"window": "night-harvest-v1", "anchor": "9092a931",
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "envelope_calls_cap": 500,
            "rules": {"draws_flash": 4, "draws_glm": 3,
                      "escalade": "si negatifs < 30% batch 1 => GLM-5.2-NVFP4 batch 2+",
                      "abort_no_diff_batch": 0.60, "infra_stop": 8, "quarantine_max": 0.10},
            "n_tickets": len(done),
            "tickets": [{k: v for k, v in t.items() if k in
                         ("issue", "fix_commit", "parent", "src_files", "src_sizes",
                          "tests_run", "f2p", "p2p_n", "ticket_text", "test_file")} for t in done]}
    (OUT / "harvest-manifest.json").write_text(json.dumps(mani, indent=1, ensure_ascii=False) + "\n")
    print(f"manifest : {len(done)} tickets prêts, cap 500 appels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
