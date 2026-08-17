#!/usr/bin/env python3
"""Collecte tickets RÉELS multi-repos (v13) : Flash / GLM / Qwen3.8.

Boucle : ticket validé (verified.json du repo) -> worktree au parent ->
prompt (ticket_text SANS solution + F2P/P2P nommés + sources buggy) ->
tirages auteur -> extract+apply sha-vérifié -> tests (runner du repo, timeout
240) -> issue groundée -> cleanup. Cap global 900 (v13 ratifié) ; infra-stop
>=8 ; idempotence par (issue, auteur).
Run: uv run python scripts/act2/real_ticket_harvest.py --author DeepSeek-V4-Flash --draws 4 [--repo omniroute|zod|date-fns|all] [--limit N] [--hard-first]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NH = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest"
HOST = "Kimsufi-standard"
CAP = 900
FULL_MAX_TOTAL_LINES = 1400
REPOS = {
    "omniroute": {"remote": "~/OmniRoute", "wt_root": "~/OmniRoute-harvest",
                  "runner": "node",
                  "cmd": "cd {wt} && timeout 240 node --import tsx/esm --test --test-reporter=tap {tests} 2>&1"},
    "zod": {"remote": "~/zod-source", "wt_root": "~/Zod-harvest",
            "runner": "vitest4",
            "cmd": "cd {wt} && timeout 240 npx vitest run --no-cache --reporter=tap {tests} 2>&1"},
    "date-fns": {"remote": "~/date-fns-source", "wt_root": "~/DateFns-harvest",
                 "runner": "vitest8",
                 "cmd": "cd {wt}/pkgs/core && timeout 240 npx vitest run --no-cache --reporter=tap {tests_rel} 2>&1"},
}
LINK_NM = {
    "omniroute": "ln -sfn ~/OmniRoute/node_modules {wt}/node_modules",
    "zod": "ln -sfn ~/zod-source/node_modules {wt}/node_modules",
    "date-fns": ("ln -sfn ~/date-fns-source/node_modules {wt}/node_modules && "
                 "ln -sfn ~/date-fns-source/pkgs/core/node_modules {wt}/pkgs/core/node_modules 2>/dev/null || true"),
}

spec = importlib.util.spec_from_file_location("gg", ROOT / "scripts" / "act2" / "genfam_gen.py")
gg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gg)
_specx = importlib.util.spec_from_file_location("prx", ROOT / "scripts" / "act2" / "pilot_run.py")
PRX = importlib.util.module_from_spec(_specx)
sys.modules["pilot_run"] = PRX
_specx.loader.exec_module(PRX)
MODEL = {"m": ""}


def call_t07(prompt: str) -> dict:
    key = os.environ.get("LI_GALERE_KEY") or os.environ.get("OPENCODE_GALERE_KEY")
    body = json.dumps({"model": MODEL["m"], "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.7, "max_tokens": 16000})
    cmd = ["curl", "-sS", "--max-time", "580", "-X", "POST", gg.pr.GALERE,
           "-H", "Content-Type: application/json", "-H", "User-Agent: opencode/1.0",
           "--data-binary", "@-"]
    if key:
        cmd += ["-H", f"Authorization: Bearer {key}"]
    p = subprocess.run(cmd, input=body.encode(), capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"curl rc={p.returncode} {p.stderr.decode()[-200:]}")
    j = json.loads(p.stdout.decode())
    if "choices" not in j:
        raise RuntimeError(str(j)[:200])
    mm = j["choices"][0]["message"]
    return {"text": (mm.get("content") or "") + "\n" +
            (mm.get("reasoning") or mm.get("reasoning_content") or ""), "usage": j.get("usage", {})}


def run(cmd: str, t: int = 600) -> str:
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
    return failed, passed


def budget_used() -> int:
    f = NH / "call-counter.jsonl"
    return sum(1 for l in f.read_text().splitlines() if l.strip()) if f.is_file() else 0


def count_call(row: dict) -> None:
    with (NH / "call-counter.jsonl").open("a") as fh:
        fh.write(json.dumps({**row, "ts": datetime.now(UTC).isoformat()}, ensure_ascii=False) + "\n")


def load_verified(repo: str | None) -> list[dict]:
    out = []
    if repo and repo != "all":
        f = NH / repo / "verified.json"
        if f.is_file():
            out += json.loads(f.read_text())
        return out
    legacy = NH / "verified.json"
    if legacy.is_file() and repo in (None, "all"):
        out += [dict(t, repo=t.get("repo", "omniroute")) for t in json.loads(legacy.read_text())]
    for r in ("omniroute", "zod", "date-fns"):
        if r == repo or repo in (None, "all"):
            f = NH / r / "verified.json"
            if f.is_file():
                for t in json.loads(f.read_text()):
                    t.setdefault("repo", r)
                    out.append(t)
    return out


def build_prompt(t: dict, srcs: dict[str, str]) -> str:
    lines = [f"REAL TICKET ({t['repo']} issue {t['issue']}): {t.get('ticket_text', '')[:600]}",
             "", "FAILING TESTS (must pass after a correct fix):"]
    lines += [f"- {f}" for f in t["f2p"]]
    lines += ["", "TESTS THAT CURRENTLY PASS (must keep passing):"]
    lines += [f"- {f}" for f in t.get("p2p_names", [])[:8]] if t.get("p2p_names") else ["(le reste de la suite)"]
    total = sum(len(v.splitlines()) for v in srcs.values())
    disclosed = total > FULL_MAX_TOTAL_LINES
    for path, content in srcs.items():
        ls = content.splitlines()
        if disclosed:
            lines.append(f"\nFILE {path} ({len(ls)} lines, TRONQUÉ début+fin):\n```\n" +
                         "\n".join(ls[:900]) + "\n...[TRONQUÉ]...\n" + "\n".join(ls[-300:]) + "\n```")
        else:
            lines.append(f"\nFILE {path} (full):\n```\n{content}\n```")
    lines.append("\nReturn ONLY a unified diff inside ```diff fences, real a/ b/ paths, "
                 "git-apply compatible. Minimal fix.")
    return "\n".join(lines) + (" [DIVULGATION: fichiers tronqués]" if disclosed else "")


def measure(t: dict, cid: str, diff: str, wt: str, repo: str) -> dict:
    prof = REPOS[repo]
    out = {"id": cid, "issue": t["issue"], "repo": repo}
    tmp = NH / f".tmp-{abs(hash(cid)) % 10**8}.diff"
    tmp.write_text(diff if diff.endswith("\n") else diff + "\n")
    subprocess.run(["scp", "-q", str(tmp), f"{HOST}:/tmp/hv-{abs(hash(cid)) % 10**8}.diff"],
                   capture_output=True, check=False, timeout=120)
    tmp.unlink(missing_ok=True)
    rf = f"/tmp/hv-{abs(hash(cid)) % 10**8}.diff"
    sha_pre = {f: run(f"sha256sum {wt}/{f} | cut -c1-16").strip() for f in t["src_files"]}
    ap = run(f"cd {wt} && git apply --recount {rf} 2>&1")
    applied = any(sha_pre[f] != run(f"sha256sum {wt}/{f} | cut -c1-16").strip() for f in sha_pre)
    mode = "strict-git" if applied else None
    if not applied:
        run(f"cd {wt} && patch -p1 -l --fuzz=3 -s < {rf} 2>&1")
        applied = any(sha_pre[f] != run(f"sha256sum {wt}/{f} | cut -c1-16").strip() for f in sha_pre)
        mode = "fuzz" if applied else None
    out["applied"] = applied
    out["apply_mode"] = mode
    if not applied:
        out["apply_err"] = ap[-200:]
        run(f"cd {wt} && git checkout -- . && rm -f {rf}", t=120)
        return out
    tests = " ".join(t["tests_run"])
    cmd = prof["cmd"].format(wt=wt, tests=tests, tests_rel=tests.replace("pkgs/core/", "", 1))
    raw = run(cmd, t=420)
    failed, passed = parse_leaves(raw, prof["runner"])
    f2p_set = set(t["f2p"])
    f2p_red = sorted(f2p_set & set(failed))
    p2p_failed = [x for x in failed if x not in f2p_set]
    out.update({"f2p_red": f2p_red[:8], "p2p_failed": p2p_failed[:6], "n_passed": passed,
                "y": 1 if (not f2p_red and not p2p_failed) else 0})
    run(f"cd {wt} && git checkout -- . && rm -f {rf}", t=120)
    return out


def process_ticket(t: dict, draws: int, results_fh, consec_err: dict) -> dict:
    repo = t.get("repo", "omniroute")
    prof = REPOS[repo]
    wt = f"{prof['wt_root']}/hv-{abs(hash(t['issue'])) % 10**8}-{MODEL['m'].split('-')[0].lower()}"
    srcs = {}
    for f in t["src_files"]:
        srcs[f] = run(f"cd {prof['remote']} && git show {t['parent']}:{f}")
    prompt = build_prompt(t, srcs)
    run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null; "
        f"git worktree add {wt} {t['parent']} >/dev/null 2>&1; " +
        LINK_NM[repo].format(wt=wt) +
        f"; cd {wt} && git checkout {t['fix_commit']} -- {' '.join(t['tests_run'])} 2>/dev/null")
    tdir = NH / "tickets" / f"v13-{repo}-{abs(hash(t['issue'])) % 10**8}"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "prompt.txt").write_text(prompt)
    author_tag = MODEL["m"].split("-")[0].lower()
    out = {"issue": t["issue"], "repo": repo, "draws": []}
    draw_offset = int(os.environ.get("HARVEST_DRAW_OFFSET", "0"))
    for d in range(1 + draw_offset, draws + 1 + draw_offset):
        if budget_used() >= CAP:
            out["budget_stop"] = True
            break
        cid = f"v13-{repo}-{author_tag}-{t['issue'][-20:]}-d{d}"
        try:
            g = call_t07(prompt)
            consec_err["n"] = 0
        except Exception as e:  # noqa: BLE001
            consec_err["n"] += 1
            count_call({"slot": cid, "model": MODEL["m"], "error": str(e)[:200]})
            out["draws"].append({"id": cid, "error": str(e)[:200]})
            if consec_err["n"] >= 8:
                out["infra_stop"] = True
                break
            continue
        count_call({"slot": cid, "model": MODEL["m"], "usage": g.get("usage"), "repo": repo})
        san = PRX.extract_diff_sanitized(g["text"])
        row = {"id": cid, "model": MODEL["m"], "reply_len": len(g["text"])}
        if san:
            (tdir / f"d{d}.diff").write_text(san + "\n")
            row.update(measure(t, cid, san + "\n", wt, repo))
        else:
            row["applied"] = False
            row["reason"] = "pas-de-diff-extrable"
        out["draws"].append(row)
        results_fh.write(json.dumps({**row, "issue": t["issue"], "repo": repo,
                                     "prompt_sha256": sha256(prompt.encode()).hexdigest()[:16],
                                     "ticket": t["test_file"], "author": MODEL["m"], "draw": d,
                                     "window": "coverage-ts-v13"}, ensure_ascii=False) + "\n")
        results_fh.flush()
    run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null; git worktree prune 2>/dev/null", t=120)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", default="DeepSeek-V4-Flash")
    ap.add_argument("--draws", type=int, default=4)
    ap.add_argument("--repo", default="all")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--hard-first", action="store_true")
    ap.add_argument("--redraw", action="store_true",
                    help="re-tirages sur tickets déjà récoltés (draws décalés, mêmes auteurs possibles)")
    args = ap.parse_args()
    MODEL["m"] = args.author
    verified = load_verified(args.repo)
    results = NH / "harvest-results-v13.jsonl"
    excl_f = NH / "exclude.json"
    excl = set(json.loads(excl_f.read_text())) if excl_f.is_file() else set()
    done_pairs = set() if args.redraw else {(j["issue"], j["author"]) for l in results.read_text().splitlines() if l.strip()
                  for j in [json.loads(l)] if "issue" in j and "author" in j and j.get("id") not in excl} if results.is_file() else set()
    # héritage nuit : les issues déjà récoltées la nuit comptent comme faites (mêmes tickets omniroute)
    legacy = NH / "harvest-results.jsonl"
    if legacy.is_file():
        for l in legacy.read_text().splitlines():
            if '"issue"' in l:
                j = json.loads(l)
                done_pairs.add((j.get("issue"), j.get("author")))
    todo = [t for t in verified if (t["issue"], MODEL["m"]) not in done_pairs]
    if args.redraw:
        # cibler les tickets ayant produit >=2 négatifs (classes discriminantes)
        neg_by_issue = {}
        if results.is_file() and (NH / "harvest-results-v13.jsonl").is_file():
            for l in (NH / "harvest-results-v13.jsonl").read_text().splitlines():
                if '"issue"' in l:
                    j = json.loads(l)
                    if j.get("y") == 0:
                        neg_by_issue[j["issue"]] = neg_by_issue.get(j["issue"], 0) + 1
        todo = [t for t in todo if neg_by_issue.get(t["issue"], 0) >= 2]
    if args.hard_first:
        todo.sort(key=lambda t: -(len(t.get("f2p", [])) * 1000 + t.get("diff_lines", 0)))
    else:
        todo.sort(key=lambda t: t.get("diff_lines", 0))
    todo = todo[:args.limit]
    print(f"harvest v13 : {len(todo)} tickets ({args.repo}), auteur {args.author}, cap {budget_used()}/{CAP}")
    consec = {"n": 0}
    with results.open("a") as fh:
        for i, t in enumerate(todo):
            print(f"[{i+1}/{len(todo)}] {t['repo']} #{t['issue'][-38:]} ({len(t['f2p'])} F2P)…", flush=True)
            r = process_ticket(t, args.draws, fh, consec)
            ok = sum(1 for x in r["draws"] if x.get("applied"))
            nd = sum(1 for x in r["draws"] if not x.get("applied") and "error" not in x)
            neg = sum(1 for x in r["draws"] if x.get("y") == 0)
            print(f"    ok={ok} nodiff={nd} neg={neg}" +
                  (" INFRA-STOP" if r.get("infra_stop") else "") +
                  (" BUDGET-STOP" if r.get("budget_stop") else ""), flush=True)
            if r.get("infra_stop") or r.get("budget_stop"):
                break
    print("HARVEST V13 BATCH DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
