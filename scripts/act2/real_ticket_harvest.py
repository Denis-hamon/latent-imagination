#!/usr/bin/env python3
"""NIGHT-HARVEST-v1 — harnais de collecte tickets réels (cap global 500).

Boucle : ticket validé (verified.json) -> worktree au parent -> prompt
(ticket_text SANS la solution + F2P/P2P nommés + sources buggy entières si
<=1400 lignes totales, sinon head/tail divulgué) -> N tirages auteur ->
extract+apply sha-vérifié -> node:test F2P+P2P -> issue groundée -> cleanup.

Règles pré-enregistrées (9092a931) : cap dur 500 appels (refus au 501e
journalisé), infra-stop >=8 erreurs endpoint consécutives, abort batch si
no-diff >60 %, escalade GLM si négatifs batch 1 <30 % (géré par l'orchestrateur).
Run: uv run python scripts/act2/real_ticket_harvest.py --author DeepSeek-V4-Flash --draws 4 [--limit N]
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
TICKETS = NH / "tickets"
HOST = "Kimsufi-standard"
REPO = "~/OmniRoute"
WT_ROOT = "~/OmniRoute-harvest"
CAP = 500
FULL_MAX_TOTAL_LINES = 1400

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


def run(cmd: str, t: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                          capture_output=True, text=True, check=False, timeout=t)


def budget_used() -> int:
    f = NH / "call-counter.jsonl"
    return sum(1 for l in f.read_text().splitlines() if l.strip()) if f.is_file() else 0


def count_call(row: dict) -> None:
    with (NH / "call-counter.jsonl").open("a") as fh:
        fh.write(json.dumps({**row, "ts": datetime.now(UTC).isoformat()}, ensure_ascii=False) + "\n")


def build_prompt(t: dict, srcs: dict[str, str]) -> str:
    lines = [f"REAL TICKET (issue #{t['issue']}): {t['ticket_text']}",
             "", "FAILING TESTS (must pass after a correct fix):"]
    lines += [f"- {f}" for f in t["f2p"]]
    if t.get("p2p_names"):
        lines += ["", "TESTS THAT CURRENTLY PASS (must keep passing):"]
        lines += [f"- {f}" for f in t["p2p_names"][:8]]
    total = sum(len(v.splitlines()) for v in srcs.values())
    disclosed = total > FULL_MAX_TOTAL_LINES
    for path, content in srcs.items():
        ls = content.splitlines()
        if disclosed:
            head = "\n".join(ls[:900])
            tail = "\n".join(ls[-300:])
            lines.append(f"\nFILE {path} ({len(ls)} lines, TRONQUÉ milieu divulgué):\n```\n{head}\n...[TRONQUÉ]...\n{tail}\n```")
        else:
            lines.append(f"\nFILE {path} (full):\n```\n{content}\n```")
    lines.append("\nReturn ONLY a unified diff inside ```diff fences, real a/ b/ paths, "
                 "git-apply compatible. Minimal fix.")
    return "\n".join(lines) + ((" [DIVULGATION: fichiers tronqués]") if disclosed else "")


def measure(wt: str, t: dict, cid: str, diff: str) -> dict:
    out = {"id": cid, "issue": t["issue"]}
    run(f"scp -q /dev/stdin {HOST}:/tmp/hv-{cid}.diff", t=60) if False else None
    tmp = NH / f".tmp-{cid}.diff"
    tmp.write_text(diff if diff.endswith("\n") else diff + "\n")
    subprocess.run(["scp", "-q", str(tmp), f"{HOST}:/tmp/hv-{cid}.diff"],
                   capture_output=True, check=False, timeout=120)
    tmp.unlink(missing_ok=True)
    sha_pre = {}
    for f in t["src_files"]:
        sha_pre[f] = run(f"sha256sum {wt}/{f} | cut -c1-16").stdout.strip()
    ap = run(f"cd {wt} && git apply --recount /tmp/hv-{cid}.diff 2>&1")
    applied = any(sha_pre[f] != run(f"sha256sum {wt}/{f} | cut -c1-16").stdout.strip() for f in sha_pre)
    mode = "strict-git" if applied else None
    if not applied:
        run(f"cd {wt} && patch -p1 -l --fuzz=3 -s < /tmp/hv-{cid}.diff 2>&1")
        applied = any(sha_pre[f] != run(f"sha256sum {wt}/{f} | cut -c1-16").stdout.strip() for f in sha_pre)
        mode = "fuzz" if applied else None
    out["applied"] = applied
    out["apply_mode"] = mode
    if not applied:
        out["apply_err"] = ap.stdout[-200:]
        return out
    tests = " ".join(t["tests_run"])
    raw = run(f"cd {wt} && timeout 240 node --import tsx/esm --test --test-reporter=tap {tests} 2>&1", t=400).stdout
    failed, passed = [], 0
    for line in raw.splitlines():
        l = line.strip()
        if l.startswith("not ok "):
            failed.append(l[7:].split(" # ")[0].strip())
        elif l.startswith("ok "):
            passed += 1
    f2p_set = set(t["f2p"])
    f2p_red = sorted(f2p_set & set(failed))
    p2p_failed = [x for x in failed if x not in f2p_set]
    out.update({"f2p_red": f2p_red[:8], "p2p_failed": p2p_failed[:6], "n_passed": passed,
                "y": 1 if (not f2p_red and not p2p_failed) else 0})
    run(f"cd {wt} && git checkout -- . && rm -f /tmp/hv-{cid}.diff", t=120)
    return out


def process_ticket(t: dict, author: str, draws: int, results_fh, consec_err: dict) -> dict:
    wt = f"{WT_ROOT}/hv-{t['issue']}"
    cid_base = f"t{t['issue']}"
    srcs = {}
    for f in t["src_files"]:
        c = run(f"cd {REPO} && git show {t['parent']}:{f}").stdout
        srcs[f] = c
    prompt = build_prompt(t, srcs)
    run(f"cd {REPO} && git worktree remove --force {wt} 2>/dev/null; git worktree add {wt} {t['parent']} >/dev/null 2>&1; ln -sfn ~/OmniRoute/node_modules {wt}/node_modules; cd {wt} && git checkout {t['fix_commit']} -- {' '.join(t['tests_run'])} 2>/dev/null")
    tdir = TICKETS / cid_base
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "prompt.txt").write_text(prompt)
    out = {"issue": t["issue"], "draws": []}
    for d in range(1, draws + 1):
        if budget_used() >= CAP:
            out["budget_stop"] = True
            break
        cid = f"{cid_base}-{author.split('-')[0].lower()}-d{d}"
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
        count_call({"slot": cid, "model": MODEL["m"], "usage": g.get("usage")})
        san = PRX.extract_diff_sanitized(g["text"])
        row = {"id": cid, "model": MODEL["m"], "reply_len": len(g["text"])}
        if san:
            (tdir / f"d{d}.diff").write_text(san + "\n")
            row.update(measure(wt, t, cid, san + "\n"))
        else:
            row["applied"] = False
            row["reason"] = "pas-de-diff-extrable"
        out["draws"].append(row)
        results_fh.write(json.dumps({**row, "issue": t["issue"], "prompt_sha256": sha256(prompt.encode()).hexdigest()[:16],
                                     "ticket": t["test_file"], "author": MODEL["m"], "draw": d,
                                     "window": "night-harvest-v1"}, ensure_ascii=False) + "\n")
        results_fh.flush()
    run(f"cd {REPO} && git worktree remove --force {wt} 2>/dev/null; git worktree prune", t=120)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", default="DeepSeek-V4-Flash")
    ap.add_argument("--draws", type=int, default=4)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--hard-first", action="store_true",
                    help="priorité aux tickets difficiles (F2P nombreux + gros diff)")
    args = ap.parse_args()
    MODEL["m"] = args.author
    verified = json.loads((NH / "verified.json").read_text())
    results = NH / "harvest-results.jsonl"
    excl = set(json.loads((NH / "exclude.json").read_text())) if (NH / "exclude.json").is_file() else set()
    done_pairs = {(j["issue"], j["author"]) for l in results.read_text().splitlines() if l.strip()
                  for j in [json.loads(l)]
                  if "issue" in j and "author" in j and j.get("id") not in excl} if results.is_file() else set()
    todo = [t for t in verified if (t["issue"], MODEL["m"]) not in done_pairs]
    if args.hard_first:
        todo.sort(key=lambda t: -(len(t.get("f2p", [])) * 1000 + t.get("diff_lines", 0)))
    else:
        todo.sort(key=lambda t: sum(t.get("src_sizes", {}).values() or [t["diff_lines"]]))
    todo = todo[:args.limit]
    print(f"harvest : {len(todo)} tickets (déjà faits: {len(done_pairs)}), cap global {budget_used()}/{CAP}")
    consec = {"n": 0}
    with results.open("a") as fh:
        for i, t in enumerate(todo):
            print(f"[{i+1}/{len(todo)}] ticket #{t['issue']} ({len(t['f2p'])} F2P)…", flush=True)
            r = process_ticket(t, args.author, args.draws, fh, consec)
            nd = sum(1 for x in r["draws"] if not x.get("applied") and "error" not in x)
            ok = sum(1 for x in r["draws"] if x.get("applied"))
            neg = sum(1 for x in r["draws"] if x.get("y") == 0)
            print(f"    ok={ok} nodiff={nd} neg={neg}" + (" INFRA-STOP" if r.get("infra_stop") else "") + (" BUDGET-STOP" if r.get("budget_stop") else ""), flush=True)
            if r.get("infra_stop") or r.get("budget_stop"):
                break
    print("HARVEST BATCH DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
