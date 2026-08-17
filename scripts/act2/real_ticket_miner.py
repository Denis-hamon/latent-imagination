#!/usr/bin/env python3
"""Mineur de tickets RÉELS multi-repos (night-harvest-v1 puis v13).

Profils supportés : omniroute (node:test), zod (vitest racine), date-fns
(vitest depuis pkgs/core). Discovery = test ajouté par un commit qui touche
aussi des fichiers source ; filtres de surface ; contrôle RED->GREEN avec le
runner du repo. Run:
  uv run python scripts/act2/real_ticket_miner.py --repo zod --stage discover
  uv run python scripts/act2/real_ticket_miner.py --repo zod --stage verify --limit N
  uv run python scripts/act2/real_ticket_miner.py --repo zod --stage manifest
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NH = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest"
HOST = "Kimsufi-standard"

PROFILES = {
    "omniroute": {
        "remote": "~/OmniRoute", "wt_root": "~/OmniRoute-harvest",
        "find_tests": "find tests/unit -type f -name '*.test.ts'",
        "src_filter": "open-sse/",
        "runner": "node",
        "cmd": "cd {wt} && timeout 240 node --import tsx/esm --test --test-reporter=tap {tests} 2>&1",
        "link_nm": "ln -sfn ~/OmniRoute/node_modules {wt}/node_modules",
    },
    "zod": {
        "remote": "~/zod-source", "wt_root": "~/Zod-harvest",
        "find_tests": "find packages/zod/src/v4/classic/tests packages/zod/src/v4/core/tests packages/zod/src/v4/mini/tests -name \x27*.test.ts\x27 2>/dev/null | head -600",
        "src_filter": "packages/zod/src/",
        "runner": "vitest4",
        "cmd": "cd {wt} && timeout 240 npx vitest run --no-cache --reporter=tap {tests} 2>&1",
        "link_nm": "ln -sfn ~/zod-source/node_modules {wt}/node_modules",
    },
    "kimi": {
        "remote": "~/kimi-code", "wt_root": "~/Kimi-harvest",
        "find_tests": "find packages apps -path '*/node_modules' -prune -o -path '*/dist' -prune -o -name '*.test.ts' -print -o -name '*.test.mts' -print 2>/dev/null | head -700",
        "src_filter": "packages/",
        "runner": "vitan",
        "cmd": "cd {wt} && timeout 240 pnpm exec vitest run --no-cache --reporter=tap {tests} 2>&1",
        "link_nm": "cd {wt} && pnpm install --ignore-scripts --prefer-offline --config.engine-strict=false >/dev/null 2>&1",
    },
    "qwen": {
        "remote": "~/qwen-code", "wt_root": "~/Qwen-harvest",
        "find_tests": "find packages -path '*/node_modules' -prune -o -name '*.test.ts' -print 2>/dev/null | grep -v integration | head -700",
        "src_filter": "packages/",
        "runner": "vitan",
        "cmd": "cd {wt} && timeout 240 npx vitest run --no-cache --reporter=tap {tests} 2>&1",
        "link_nm": "ln -sfn ~/qwen-code/node_modules {wt}/node_modules",
    },
    "nx": {
        "remote": "~/nx", "wt_root": "~/Nx-harvest",
        "find_tests": "find packages -path '*/node_modules' -prune -o -name '*.spec.ts' -print 2>/dev/null | grep -v -E 'dist|e2e|integration|/src/plugins/' | head -700",
        "src_filter": "packages/",
        "runner": "jest",
        "cmd": ("first=$(echo \"{tests}\" | awk '{{print $1}}'); pkg=$(echo $first | cut -d/ -f1-2); "
                "cd {wt} && timeout 300 npx jest --config $pkg/jest.config.cts --verbose {tests} 2>&1"),
        "link_nm": ("ln -sfn ~/nx/node_modules {wt}/node_modules; for d in {wt}/packages/*/; do "
                    "b=$(basename $d); [ -d ~/nx/packages/$b/node_modules ] && "
                    "ln -sfn ~/nx/packages/$b/node_modules $d/node_modules || true; done"),
    },
    "tanquery": {
        "remote": "~/TanStack-query", "wt_root": "~/TanQuery-harvest",
        "find_tests": "find packages -path '*/node_modules' -prune -o -path '*/__tests__' -name '*.test.ts*' -print 2>/dev/null | grep -v codemods | head -700",
        "src_filter": "packages/query-core/src/ packages/query-persist-client-core/src/ packages/react-query/src/",
        "runner": "vitan",
        "cmd": "cd {wt} && timeout 240 pnpm exec vitest run --no-cache --reporter=tap {tests} 2>&1",
        "link_nm": "ln -sfn ~/TanStack-query/node_modules {wt}/node_modules",
    },
    "cqe": {
        "remote": "~/connectrpc-connect-query-es", "wt_root": "~/Cqe-harvest",
        "find_tests": "find packages -path '*/node_modules' -prune -o -name '*.test.ts' -print 2>/dev/null | grep -v integration | head -400",
        "src_filter": "packages/connect-query-core/src/ packages/connect-query/src/",
        "runner": "vitan",
        "cmd": "cd {wt}/packages/connect-query-core && timeout 240 npx vitest run --no-cache --reporter=tap {tests_rel} 2>&1",
        "tests_rel_prefix": "packages/connect-query-core/",
        "link_nm": "ln -sfn ~/connectrpc-connect-query-es/node_modules {wt}/node_modules; for pk in connect-query-core connect-query; do ln -sfn ~/connectrpc-connect-query-es/packages/$pk/node_modules {wt}/packages/$pk/node_modules 2>/dev/null || true; done",
    },
    "epv": {
        "remote": "~/vitest-dev-eslint-plugin-vitest", "wt_root": "~/Epv-harvest",
        "find_tests": "find src -name '*.test.ts' 2>/dev/null | head -300",
        "src_filter": "src/",
        "runner": "vitan",
        "cmd": "cd {wt} && timeout 240 pnpm exec vitest run --no-cache --reporter=tap {tests} 2>&1",
        "link_nm": "ln -sfn ~/vitest-dev-eslint-plugin-vitest/node_modules {wt}/node_modules",
    },
    "qkf": {
        "remote": "~/lukemorales-query-key-factory", "wt_root": "~/Qkf-harvest",
        "find_tests": "find src -name '*.spec.ts' -o -name '*.test.ts' 2>/dev/null | head -100",
        "src_filter": "src/",
        "runner": "vitan",
        "cmd": "cd {wt} && timeout 240 pnpm exec vitest run --no-cache --reporter=tap {tests} 2>&1",
        "link_nm": "ln -sfn ~/lukemorales-query-key-factory/node_modules {wt}/node_modules",
    },
    "nextjs": {
        "remote": "~/nextjs", "wt_root": "~/Nextjs-harvest",
        "find_tests": "find test/unit packages/next/src -name '*.test.ts' -o -name '*.test.tsx' 2>/dev/null | grep -v node_modules | head -700",
        "src_filter": "packages/next/src/",
        "runner": "jest",
        "cmd": "cd {wt} && timeout 300 npx jest --verbose --silent {tests} 2>&1",
        "link_nm": "ln -sfn ~/nextjs/node_modules {wt}/node_modules && ln -sfn ~/nextjs/packages/next/node_modules {wt}/packages/next/node_modules 2>/dev/null || true",
    },
    "date-fns": {
        "remote": "~/date-fns-source", "wt_root": "~/DateFns-harvest",
        "find_tests": "find pkgs/core/src -maxdepth 2 -name test.ts -type f | head -400",
        "src_filter": "pkgs/core/src/",
        "runner": "vitest8",
        "cmd": "cd {wt}/pkgs/core && timeout 240 npx vitest run --no-cache --reporter=tap {tests_rel} 2>&1",
        "link_nm": "ln -sfn ~/date-fns-source/node_modules {wt}/node_modules && ln -sfn ~/date-fns-source/pkgs/core/node_modules {wt}/pkgs/core/node_modules 2>/dev/null",
    },
}
MAX_SRC_FILES, MAX_DIFF_LINES, MAX_FILE_LINES, MAX_TOTAL = 5, 600, 1200, 3000  # axe 4 v13 (disclosure) : surface élargie


def run(cmd: str, t: int = 900) -> str:
    try:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                           capture_output=True, text=True, check=False, timeout=t)
        return r.stdout
    except subprocess.TimeoutExpired:
        return ""


def parse_leaves(raw: str, kind: str) -> tuple[list[str], int]:
    failed, passed = [], 0
    for line in raw.splitlines():
        if kind == "node":
            l = line.strip()
            if l.startswith("not ok "):
                failed.append(l[7:].split(" # ")[0].strip())
            elif l.startswith("ok "):
                passed += 1
        elif kind == "vitest4":
            if not line.startswith("    ") or line.rstrip().endswith("{"):
                continue
            l = line.strip()
            if l.startswith("not ok "):
                failed.append(l[7:].split(" # ")[0].split(" > ")[-1].strip())
            elif l.startswith("ok "):
                passed += 1
        elif kind == "vitest8":
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if indent < 8 or line.rstrip().endswith("{"):
                continue
            if stripped.startswith("not ok "):
                failed.append(stripped[7:].split(" # ")[0].split(" > ")[-1].strip())
            elif stripped.startswith("ok "):
                passed += 1
        elif kind == "jest":
            # jest --verbose : feuilles "✓/✕ nom (N ms)" sous les lignes PASS/FAIL
            stripped = line.strip()
            if stripped.startswith(("\u2713", "✓")):
                passed += 1
            elif stripped.startswith(("\u2715", "✕")):
                nm = stripped[1:].strip()
                nm = nm.rsplit(" (", 1)[0].strip()
                failed.append(nm)
        elif kind == "vitan":
            # TAP vitest imbriqué (kimi/qwen) : toute feuille ok/not ok, quel que
            # soit le niveau d'indent ; les blocs parents finissent par "{"
            stripped = line.strip()
            if line.rstrip().endswith("{"):
                continue
            if stripped.startswith("not ok "):
                failed.append(stripped[7:].split(" # ")[0].split(" > ")[-1].strip())
            elif stripped.startswith("ok "):
                passed += 1
    return failed, passed


def discover(repo: str) -> list[dict]:
    p = PROFILES[repo]
    tests = run(f"cd {p['remote']} && {p['find_tests']}", t=300).split()
    print(f"{repo}: {len(tests)} fichiers test détectés")
    remote_script = f"""#!/bin/bash
cd {p['remote']}
OUT=/tmp/discovery_{repo}.tsv
> "$OUT"
> /tmp/tflist_{repo}.txt
for t in {' '.join(f'"{t}"' for t in tests[:400])}; do echo "$t" >> /tmp/tflist_{repo}.txt; done
git log --reverse --diff-filter=A --format='@@%H|%s' --name-only -- $(cat /tmp/tflist_{repo}.txt | tr '\n' ' ') 2>/dev/null > /tmp/addlog_{repo}.txt
cur_add=""; cur_subj=""
declare -A FA FS
while IFS= read -r line; do
  case "$line" in
    @@*) cur_add="${{line#@@}}"; cur_subj="${{cur_add#*|}}"; cur_add="${{cur_add%%|*}}";;
    *)
      case "$line" in
        *.test.ts|*.test.mts|*.spec.ts|*.spec.tsx|*/test.ts)
          if [ -z "${{FA[$line]:-}}" ]; then FA[$line]="$cur_add"; FS[$line]="$cur_subj"; fi;;
      esac;;
  esac
done < /tmp/addlog_{repo}.txt
echo "distinct testfiles: ${{#FA[@]}}" >&2
for tf in "${{!FA[@]}}"; do
  add="${{FA[$tf]}}"
  src=$(git diff --name-only "${{add}}^" "$add" -- {p['src_filter']} 2>/dev/null | grep -E '\\.(ts|mts)$' | grep -v -i test | head -5)
  [ -z "$src" ] && continue
  nsrc=$(echo "$src" | wc -l)
  [ "$nsrc" -gt {MAX_SRC_FILES} ] && continue
  dl=$(git diff "${{add}}^" "$add" -- $src 2>/dev/null | wc -l)
  [ "$dl" -gt {MAX_DIFF_LINES} ] && continue
  tot=0; bad=0
  for f in $src; do
    n=$(git show "${{add}}^:$f" 2>/dev/null | wc -l)
    if [ "$n" -eq 0 ] || [ "$n" -gt {MAX_FILE_LINES} ]; then bad=1; break; fi
    tot=$((tot+n))
  done
  [ "$bad" -eq 1 ] && continue
  [ "$tot" -gt {MAX_TOTAL} ] && continue
  par=$(git rev-parse "${{add}}^" 2>/dev/null)
  tst=$(git diff --name-only "${{add}}^" "$add" 2>/dev/null | grep -E '(\\.test\\.(ts|mts|tsx)$|\\.spec\\.(ts|tsx)$|/test\\.ts$)' | head -3 | tr '\n' ' ')
  subj=$(echo "${{FS[$tf]}}" | cut -c1-140)
  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$tf" "$add" "$par" "$(echo $src | tr \" \" \",\")" "$subj" "$tst" "$dl" >> "$OUT"
done
echo "candidats: $(wc -l < "$OUT")" >&2
cat "$OUT"
"""
    remote_script2 = f"""#!/bin/bash
# stratégie 2 : commits 'fix*' touchant le src + tests associés par répertoire
cd {p['remote']}
OUT2=/tmp/discovery_{repo}_fix.tsv
> "$OUT2"
git log --format='%H|%s' -i --grep='^fix' -- {p['src_filter']} 2>/dev/null | head -600 | while IFS='|' read -r add subj; do
  src=$(git diff --name-only "${{add}}^" "$add" -- {p['src_filter']} 2>/dev/null | grep -E '\\.(ts|mts)$' | grep -v -i test | head -5)
  [ -z "$src" ] && continue
  nsrc=$(echo "$src" | wc -l)
  [ "$nsrc" -gt {MAX_SRC_FILES} ] && continue
  dl=$(git diff "${{add}}^" "$add" -- $src 2>/dev/null | wc -l)
  [ "$dl" -gt {MAX_DIFF_LINES} ] && continue
  [ "$dl" -lt 8 ] && continue
  tot=0; bad=0
  for f in $src; do
    n=$(git show "${{add}}^:$f" 2>/dev/null | wc -l)
    if [ "$n" -eq 0 ] || [ "$n" -gt {MAX_FILE_LINES} ]; then bad=1; break; fi
    tot=$((tot+n))
  done
  [ "$bad" -eq 1 ] && continue
  [ "$tot" -gt {MAX_TOTAL} ] && continue
  par=$(git rev-parse "${{add}}^" 2>/dev/null)
  # tests : soit touchés par le commit, soit colocated dans les dirs des src
  tst=$(git diff --name-only "${{add}}^" "$add" 2>/dev/null | grep -E '(\\.test\\.(ts|mts|tsx)$|\\.spec\\.(ts|tsx)$|/test\\.ts$)' | head -2 | tr '\n' ' ')
  if [ -z "$(echo $tst | tr -d ' ')" ]; then
    tst=$(for f in $src; do d=$(dirname "$f"); for cand in "$d/test.ts" "$d/tests/$(basename $d).test.ts" "$d/index.test.ts"; do git show "$add:$cand" >/dev/null 2>&1 && echo "$cand"; done; done | sort -u | head -2 | tr '\n' ' ')
  fi
  [ -z "$(echo $tst | tr -d ' ')" ] && continue
  subj2=$(echo "$subj" | cut -c1-140)
  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$(echo $tst | awk '{{print $1}}')" "$add" "$par" "$(echo $src | tr ' ' ',')" "$subj2" "$tst" "$dl" >> "$OUT2"
done
echo "candidats-fix: $(wc -l < "$OUT2")" >&2
cat "$OUT2"
"""
    tmp = Path("/tmp") / f"discover_{repo}.sh"
    tmp.write_text(remote_script)
    tmp2 = Path("/tmp") / f"discover_{repo}_fix.sh"
    tmp2.write_text(remote_script2)
    subprocess.run(["scp", "-q", str(tmp), str(tmp2), f"{HOST}:/tmp/"],
                   capture_output=True, check=False, timeout=60)
    out = run(f"bash /tmp/discover_{repo}.sh", t=2400) + "\n" + run(f"bash /tmp/discover_{repo}_fix.sh", t=2400)
    cands, seen = [], set()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        tf, add, par, srcstr, subj, tests_in, dl = parts
        src = [x for x in srcstr.split(",") if x]
        tlist = sorted(set([tf] + [x for x in tests_in.split() if x]))[:3]
        key = tf.replace("/", "_")
        key = key.removesuffix(".test.ts")
        ck = (tf, add)
        if ck in seen:
            continue
        seen.add(ck)
        cands.append({"issue": f"{repo}-{key[-48:]}", "repo": repo, "test_file": tf,
                      "fix_commit": add, "parent": par, "src_files": src,
                      "diff_lines": int(dl), "tests_in_fix": tlist,
                      "commit_subject": subj})
    return cands


def changelog_text(repo: str, fix: str) -> str:
    if repo == "omniroute":
        entries = run(f"cd {PROFILES[repo]['remote']} && git show --name-only --format= {fix} -- changelog.d/ 2>/dev/null").split()
        for e in entries:
            if e.startswith("changelog.d/"):
                body = run(f"cd {PROFILES[repo]['remote']} && git show {fix}:{e} 2>/dev/null").strip()
                if body:
                    return body[:600]
    return ""


def verify_one(c: dict, relaxed_mode: bool = False) -> dict:
    repo = c["repo"]
    p = PROFILES[repo]
    wt = f"{p['wt_root']}/probe-{abs(hash(c['issue']))%10**8}"
    run(f"cd {p['remote']} && git worktree remove --force {wt} 2>/dev/null; git worktree add {wt} {c['parent']} >/dev/null 2>&1")
    run(p["link_nm"].format(wt=wt))
    tests_in = list(c["tests_in_fix"])
    # DW-52-suite : les commits qui n'ajoutent qu'UN test n'ont pas de P2P dans
    # le run-set -> veto affaibli à tort. Extension : jusqu'à 3 fichiers test
    # FRÈRES du répertoire (au parent) entrent dans le run pour fournir un P2P
    # réel (plus de fichiers = veto plus fort, pas plus faible).
    if len(tests_in) < 2:
        d0 = "/".join(tests_in[0].split("/")[:-1])
        sib = [x for x in run(
            f"cd {p['remote']} && git ls-tree --name-only {c['parent']} {d0}/ 2>/dev/null").split()
            if (x.endswith(".test.ts") or x.endswith(".test.tsx") or x.endswith(".spec.ts"))
            and d0 + "/" + x.split("/")[-1] not in tests_in]
        tests_in += [d0 + "/" + x.split("/")[-1] for x in sib[:3]]
    tests = " ".join(tests_in[:6])
    run(f"cd {wt} && git checkout {c['fix_commit']} -- {' '.join(c['tests_in_fix'])} 2>/dev/null")
    cmd = p["cmd"].format(wt=wt, tests=tests, tests_rel=(tests.replace("pkgs/core/", "", 1) if repo == "date-fns" else (tests.replace("packages/connect-query-core/", "", 1) if repo == "cqe" else tests)))
    try:
        red_raw = run(cmd, t=320)
    except Exception:  # noqa: BLE001
        red_raw = ""
    failed, passed = parse_leaves(red_raw, p["runner"])
    wt_esc = wt
    if len(failed) < 2 if relaxed_mode else len(failed) < 1 or (passed < 2 and not relaxed_mode):
        run(f"cd {p['remote']} && git worktree remove --force {wt_esc} 2>/dev/null")
        return {**c, "rejected": f"RED/P2P insuffisant : {len(failed)} F2P, {passed} P2P"}
    run(f"cd {wt_esc} && git diff {c['parent']} {c['fix_commit']} -- {' '.join(c['src_files'])} > /tmp/fix-{abs(hash(c['issue']))%10**8}.diff && git apply --recount /tmp/fix-{abs(hash(c['issue']))%10**8}.diff 2>&1 | head -2")
    try:
        green_raw = run(cmd, t=320)
    except Exception:  # noqa: BLE001
        green_raw = ""
    gfail, _ = parse_leaves(green_raw, p["runner"])
    run(f"cd {p['remote']} && git worktree remove --force {wt_esc} 2>/dev/null")
    if gfail:
        return {**c, "rejected": f"GREEN échoué au fix humain : {gfail[:3]}"}
    ticket = changelog_text(repo, c["fix_commit"]) or c["commit_subject"]
    return {**c, "f2p": sorted(set(failed)), "p2p_n": passed, "tests_run": c["tests_in_fix"],
            "ticket_text": ticket, "ok": True}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", choices=tuple(PROFILES), default="omniroute")
    ap.add_argument("--stage", choices=("discover", "verify", "verify-relaxed", "manifest"), required=True)
    ap.add_argument("--relaxed", action="store_true", help="F2P>=2, P2P>=0 (veto affaibli disclosé, axe 4 v13)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    OUT = NH / args.repo
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage == "discover":
        cands = discover(args.repo)
        (OUT / "discovered.json").write_text(json.dumps(cands, indent=1, ensure_ascii=False) + "\n")
        print(f"{len(cands)} candidats -> {OUT/'discovered.json'}")
        for c in cands[:20]:
            print(f"  {c['issue'][:48]:50} {len(c['src_files'])}F {c['diff_lines']:4}L  {c['commit_subject'][:52]}")
        return 0
    if args.stage in ("verify", "verify-relaxed"):
        cands = json.loads((OUT / "discovered.json").read_text())
        prior = json.loads((OUT / "verified.json").read_text()) if (OUT / "verified.json").is_file() else []
        pr_rej = set()
        if (OUT / "verify-rejects.jsonl").is_file():
            # rejets vérification = déterministes (RED/P2P/GREEN) sous les deux modes
            pr_rej = {json.loads(l).get("test_file") for l in
                      (OUT / "verify-rejects.jsonl").read_text().splitlines() if l.strip()}
        done_tf = {d["test_file"] for d in prior}
        cands = [c for c in cands if c["test_file"] not in done_tf
                 and c["test_file"] not in pr_rej]
        cands.sort(key=lambda c: c["diff_lines"])
        if args.limit:
            cands = cands[:args.limit]
        done = list(prior)
        nrej = 0
        for i, c in enumerate(cands):
            print(f"[{i+1}/{len(cands)}] {c['issue'][:52]} …", flush=True)
            try:
                r = verify_one(c, relaxed_mode=(args.stage == 'verify-relaxed'))
            except (subprocess.SubprocessError, OSError, ValueError) as exc:
                r = {**c, "rejected": f"exception: {str(exc)[:80]}"}
            if r.pop("ok", False):
                done.append(r)
                print(f"    VALIDÉ : {len(r['f2p'])} F2P / {r['p2p_n']} P2P")
            else:
                nrej += 1
                with (OUT / "verify-rejects.jsonl").open("a") as fh:
                    fh.write(json.dumps({k: v for k, v in r.items()}, ensure_ascii=False) + "\n")
                print(f"    REJETÉ : {r.get('rejected', '?')[:70]}")
            (OUT / "verified.json").write_text(json.dumps(done, indent=1, ensure_ascii=False) + "\n")
        if args.stage == "verify-relaxed":
            for d in done:
                d.setdefault("p2p_veto", "standard" if d.get("p2p_n", 0) >= 2 else "affaibli-disclose")
            (OUT / "verified.json").write_text(json.dumps(done, indent=1, ensure_ascii=False) + "\n")
        print(f"verify {args.repo} ({args.stage}) : {len(done)} validés au total, {nrej} rejetés ce run")
        return 0
    # manifest
    done = json.loads((OUT / "verified.json").read_text())
    mani = {"window": "coverage-ts-v13", "repo": args.repo,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "n_tickets": len(done),
            "tickets": [{k: v for k, v in t.items() if k in
                         ("issue", "repo", "fix_commit", "parent", "src_files",
                          "tests_run", "f2p", "p2p_n", "ticket_text", "test_file")}
                        for t in done]}
    (OUT / "harvest-manifest.json").write_text(json.dumps(mani, indent=1, ensure_ascii=False) + "\n")
    print(f"manifest {args.repo}: {len(done)} tickets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
