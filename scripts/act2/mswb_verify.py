#!/usr/bin/env python3
"""v27 Phase A — verify RED->GREEN Multi-SWE-bench sur notre hôte.
Recette héritée du mineur : worktree au base.sha, apply test_patch -> f2p
rouges, apply fix_patch -> f2p verts. Zéro appel LLM.
Run: uv run python scripts/act2/mswb_verify.py [--repo vuejs__core] [--limit N]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import subprocess
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NH = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest"
MSWB = ROOT / "data" / "landing" / "act2-pilot" / "mswb"
HOST = "Kimsufi-standard"

_spec = importlib.util.spec_from_file_location("rth", ROOT / "scripts" / "act2" / "real_ticket_harvest.py")
rth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rth)

PROFILES = {
    "vuejs__core": {"remote": "~/vue-core", "wt_root": "~/Vue-harvest", "runner": "vitan",
                    "cmd": "cd {wt} && timeout 300 ./node_modules/.bin/vitest run --no-cache --reporter=tap {tests} {names} 2>&1",
                    "link_nm": ("cd {wt} && rm -rf node_modules packages/*/node_modules 2>/dev/null; "
                                "timeout 300 pnpm install --ignore-scripts --prefer-offline "
                                "--config.engine-strict=false --reporter=silent >/dev/null 2>&1")},
    "sveltejs__svelte": {"remote": "~/svelte", "wt_root": "~/Svelte-harvest", "runner": "vitan",
                         "cmd": "cd {wt} && timeout 300 ./node_modules/.bin/vitest run --no-cache --reporter=tap {tests} {names} 2>&1",
                         "link_nm": "ln -sfn ~/svelte/node_modules {wt}/node_modules",
                         "suite_runner": True},
    "expressjs__express": {"remote": "~/express", "wt_root": "~/Express-mswb", "runner": "mochajson",
                           "cmd": ("cd {wt} && timeout 300 ./node_modules/.bin/mocha --require test/support/env "
                                   "--reporter json --check-leaks {tests} 2>/dev/null"),
                           "link_nm": ("cd {wt} && rm -rf node_modules 2>/dev/null; "
                                       "timeout 300 npm install --no-audit --no-fund --ignore-scripts "
                                       "--prefer-offline >/dev/null 2>&1 || true")},
    "iamkun__dayjs": {"remote": "~/dayjs", "wt_root": "~/Dayjs-mswb", "runner": "jestsuite",
                      "cmd": ("cd {wt} && for TZV in Pacific/Auckland Europe/London America/Whitehorse UTC; do "
                              "TZ=$TZV timeout 120 ./node_modules/.bin/jest --verbose {tests} 2>&1 | "
                              "grep -E '^(PASS|FAIL)|✕|✓'; done"),
                      "link_nm": "ln -sfn ~/dayjs/node_modules {wt}/node_modules"},
}


def apply_file(wt: str, patch: str, tag: str) -> str:
    """Pose par fichier scp (jamais heredoc ssh : transport corrompt les
    bytes — prouvé par sha sur dayjs 2026-08-19)."""
    import subprocess as _sp
    h = sha256(patch.encode()).hexdigest()[:10]
    tmp = pathlib.Path(f"/tmp/mswb-{tag}-{h}.diff")
    tmp.write_text(patch if patch.endswith("\n") else patch + "\n")
    rf = f"/tmp/mswb-{tag}-{h}.diff"
    _sp.run(["scp", "-q", str(tmp), f"{HOST}:{rf}"], capture_output=True, check=False, timeout=120)
    tmp.unlink(missing_ok=True)
    out = run(f"cd {wt} && (git apply --recount {rf} 2>&1) || (patch -p1 -l --fuzz=3 --batch < {rf} 2>&1); rm -f {rf}")
    return out


def run(cmd: str, t: int = 700) -> str:
    try:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                           capture_output=True, text=True, check=False, timeout=t)
        return r.stdout
    except subprocess.TimeoutExpired:
        return ""


def norm(name: str) -> str:
    n = name.split(" > ")[-1].split(" # ")[0].strip()
    n = re.sub(r"^\d+ - ", "", n).strip()
    for pre in ("should ", "it ", "test "):
        if n.lower().startswith(pre):
            n = n[len(pre):]
    return n.strip().lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="vuejs__core")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    prof = PROFILES[args.repo]
    OUT = MSWB / args.repo
    OUT.mkdir(parents=True, exist_ok=True)
    tickets = [t for t in json.loads((MSWB / "mswb-tickets.json").read_text())
               if t["repo"].replace("/", "__") == args.repo or t["repo"] == args.repo]
    if args.limit:
        tickets = tickets[:args.limit]
    verified_f = OUT / "verified-mswb.json"
    prior_raw = json.loads(verified_f.read_text()) if verified_f.is_file() else []
    prior_list = [t for t in prior_raw if isinstance(t, dict) and "issue" in t]
    prior = {t["issue"] for t in prior_list}
    done, rej = list(prior_list), 0  # fusion : jamais écraser les validations acquises
    for i, t in enumerate(tickets):
        if t["issue"] in prior:
            continue
        iid = t["issue"]
        print(f"[{i+1}/{len(tickets)}] {iid} …", flush=True)
        wt = f"{prof['wt_root']}/mswb-{abs(hash(iid)) % 10**8}"
        run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null; "
            f"git worktree add {wt} {t['parent']} >/dev/null 2>&1")
        run(prof["link_nm"].format(wt=wt))
        if prof.get("suite_runner"):
            runners = sorted({f.split("/samples/")[0] + "/test.ts"
                              for f in t["tests_run"] if "/samples/" in f})
            others = [f for f in t["tests_run"] if "/samples/" not in f]
            tests = " ".join((runners + others)[:4])
            import re as _re
            pat = "|".join(_re.escape(x) for x in t["f2p"][:8])
            names = f'-t {json.dumps(pat)}' if pat else ""
        else:
            tests = " ".join(t["tests_run"][:6])
            names = ""
        # RED : test_patch appliqué au parent, fix absent (pose par fichier scp)
        r1 = apply_file(wt, t["test_patch"], "tp")
        red_raw = run(prof["cmd"].format(wt=wt, tests=tests, names=names))
        failed_r, passed_r = rth.parse_leaves(red_raw, prof["runner"])
        nf = {norm(x) for x in failed_r}
        f2p_norm = {norm(x) for x in t["f2p"]}
        def hit(x):
            tail = x.split(":")[-1].strip()
            return any(x == fn or fn.startswith(x) or x.startswith(fn)
                       or (tail and len(tail) > 3 and (tail == fn or fn.startswith(tail) or tail.startswith(fn)))
                       for fn in nf)
        n_red_matched = sum(1 for x in f2p_norm if hit(x))
        def hit2(x):
            fg = {norm(g) for g in failed_g}
            tail = x.split(":")[-1].strip()
            return any(x == fn or fn.startswith(x) or x.startswith(fn)
                       or (tail and len(tail) > 3 and (tail == fn or fn.startswith(tail) or tail.startswith(fn)))
                       for fn in fg)
        red_all = f2p_norm and n_red_matched == len(f2p_norm)
        red_some = n_red_matched >= 1
        # GREEN : fix_patch ajouté (pose par fichier scp)
        r2 = apply_file(wt, t["fix_patch"], "fp")
        green_raw = run(prof["cmd"].format(wt=wt, tests=tests, names=names))
        failed_g, passed_g = rth.parse_leaves(green_raw, prof["runner"])
        green_ok = passed_g >= 1 and not any(hit2(x) for x in f2p_norm)
        tier = "strict" if red_all else ("partial" if red_some else None)
        run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null", t=180)
        if tier and green_ok:
            done.append({**t, "verify_tier": tier,
                         "n_red_matched": n_red_matched, "n_f2p": len(f2p_norm),
                         "p2p_n_green": passed_g, "ok": True})
            print(f"    VALIDÉ [{tier}] : {n_red_matched}/{len(f2p_norm)} F2P rouges, {passed_g} P", flush=True)
        else:
            rej += 1
            with (OUT / "verify-rejects.jsonl").open("a") as fh:
                fh.write(json.dumps({"issue": iid, "tier": tier, "green_ok": green_ok,
                                     "len_red_raw": len(red_raw), "len_green_raw": len(green_raw), "red_tail": red_raw[-200:],
                                     "n_red_matched": n_red_matched, "n_f2p": len(f2p_norm),
                                     "n_failed_red": len(failed_r), "failed_red": failed_r[:8], "apply1": r1[-120:],
                                     "apply2": r2[-120:]}, ensure_ascii=False) + "\n")
            print(f"    REJETÉ : tier={tier} green_ok={green_ok}", flush=True)
        verified_f.write_text(json.dumps(done, indent=1, ensure_ascii=False) + "\n")
    print(f"mswb-verify {args.repo} : {len(done)} validés au total (fusion), {rej} rejetés ce run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
