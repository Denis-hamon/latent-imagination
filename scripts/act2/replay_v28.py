#!/usr/bin/env python3
"""Fenêtre v28 (3a5374eb) — burst collecte 24 tickets vue MSWB vérifiés RED-GREEN.

Mitigations figées : fichiers COMPLETS (sélection total src <= 1200 lignes),
erreur git apply RÉELLE dans le feedback, F2P >= 2. Modèles : pro, qwen, glm.

Boucle : générer → poser (sha-vérifié) → tester RÉELLEMENT → feedback →
re-générer. Chaque tour = candidat intra-ticket indépendant (diff complet
depuis parent). Machinerie harvest réutilisée bit-à-bit (rth.REPOS,
parse_leaves, prof['link_nm'], timeout 240 s, restauration git en finally).

Usage: GEN_MODELS="A,B" uv run python scripts/act2/replay_agentique.py
"""
from __future__ import annotations

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
OUT = NH / "replay-v28"
ROWS = NH / "replay-rows-v28.jsonl"
COUNTER = NH / "call-counter-v28.jsonl"
SELECTION = OUT / "replay-selection-v28.json"
CAP_TOTAL = 192
CAP_MODEL = 96
MAX_TURNS = 4
FEEDBACK_CHARS = 800
PREV_DIFF_CHARS = 3000

_spec = importlib.util.spec_from_file_location("rth", ROOT / "scripts" / "act2" / "real_ticket_harvest.py")
rth = importlib.util.module_from_spec(_spec)
sys.modules["pilot_run"] = None
_spec.loader.exec_module(rth)

MODELS = {
    "pro": "DeepSeek-V4-Pro",
    "qwen": "Qwen3.8-2.4T-A95B-NVFP4",
}


def budget() -> int:
    return sum(1 for l in COUNTER.read_text().splitlines() if l.strip()) if COUNTER.is_file() else 0


def budget_model(m: str) -> int:
    if not COUNTER.is_file():
        return 0
    return sum(1 for l in COUNTER.read_text().splitlines()
               if l.strip() and json.loads(l).get("model") == m)


def count(row: dict) -> None:
    with COUNTER.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


MAX_TOTAL_SRC_LINES = 1200
REPOS_V22 = ()


def _src_total_lines(t: dict) -> int:
    prof = rth.REPOS.get(t["repo"])
    if not prof:
        return 10**9
    tot = 0
    for f in t["src_files"]:
        out = rth.run(f"cd {prof['remote']} && git show {t['parent']}:{f} 2>/dev/null | wc -l")
        try:
            tot += int(out.strip())
        except ValueError:
            return 10**9
    return tot


def select_tickets() -> list[dict]:
    vf = NH.parent / "mswb" / "vuejs__core" / "verified-mswb.json"
    cands = json.loads(vf.read_text())
    cands = [t for t in cands if t.get("ok")]
    for t in cands:
        t["repo"] = t.get("repo", "vuejs__core")
        n = _src_total_lines(t)
        t["src_total_lines"] = n if n < 10**9 else 0
    cands = [t for t in cands if t.get("src_total_lines", 0) <= MAX_TOTAL_SRC_LINES]
    cands.sort(key=lambda t: (-len(t["f2p"]), t["issue"]))
    sel = cands[:24]
    OUT.mkdir(parents=True, exist_ok=True)
    SELECTION.write_text(json.dumps({"window": "v28", "anchor": "3a5374eb9072d155",
                                     "selected_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                                     "critere": "verified-mswb RED-GREEN notre hôte ; src<=1200",
                                     "tickets": sel}, indent=1, ensure_ascii=False) + "\n")
    return sel


def run_tests(prof: dict, wt: str, t: dict) -> tuple[str, list[str], int]:
    tests = " ".join(t["tests_run"])
    cmd = prof["cmd"].format(wt=wt, tests=tests, tests_rel=tests.replace("pkgs/core/", "", 1))
    raw = rth.run(cmd, t=420)
    failed, passed = rth.parse_leaves(raw, prof["runner"])
    return raw, failed, passed


def failure_feedback(raw: str, failed: list[str], f2p_red: list[str], p2p_broken: list[str]) -> str:
    lines = [l for l in raw.splitlines() if "not ok" in l or "Error" in l or "expect(" in l or "✕" in l]
    body = "\n".join(lines)[:FEEDBACK_CHARS]
    return (f"STILL FAILING ({len(failed)}): " + "; ".join(failed[:8]) +
            f"\nF2P toujours rouges: {f2p_red[:6]}\nTests cassés par le patch: {p2p_broken[:4]}\n" + body)


FB_TMPL = ("\n\nYOUR PREVIOUS DIFF (tour {prev}, n'a pas tout réparé) :\n```diff\n{pdiff}\n```\n"
           "RÉSULTAT RÉEL DES TESTS :\n{fb}\n\nProduce a CORRECTED complete diff (same format).")


def replay_ticket(t: dict, model_key: str, model: str, fh) -> None:
    prof = rth.REPOS[t["repo"]]
    wt = f"{prof['wt_root']}/rp-{abs(hash((t['issue'], model))) % 10**8}"
    slug = t["issue"].replace("/", "_")[:80]
    tdir = OUT / f"{slug}--{model_key}"
    tdir.mkdir(parents=True, exist_ok=True)
    srcs = {f: rth.run(f"cd {prof['remote']} && git show {t['parent']}:{f}") for f in t["src_files"]}
    base_prompt = rth.build_prompt(t, srcs)
    rth.run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null; "
            f"git worktree add {wt} {t['parent']} >/dev/null 2>&1 && "
            + prof["link_nm"].format(wt=wt) +
            f" && cd {wt} && git checkout {t['fix_commit']} -- {' '.join(t['tests_run'])} 2>/dev/null")
    prev_diff, prev_fb = "", ""
    try:
        for turn in range(1, MAX_TURNS + 1):
            if budget() >= CAP_TOTAL:
                return
            prompt = base_prompt + (FB_TMPL.format(prev=turn - 1, pdiff=prev_diff[:PREV_DIFF_CHARS], fb=prev_fb) if turn > 1 else "")
            cid = f"v28-{t['repo']}-{model_key}-{slug[-40:]}-t{turn}"
            try:
                rth.MODEL["m"] = model
                g = rth.call_t07(prompt)
                count({"slot": cid, "model": model})
            except Exception as e:  # noqa: BLE001
                count({"slot": cid, "model": model, "error": str(e)[:200]})
                fh.write(json.dumps({"id": cid, "issue": t["issue"], "model": model, "turn": turn,
                                     "error": str(e)[:200], "applied": False}, ensure_ascii=False) + "\n")
                fh.flush()
                break
            san = rth.PRX.extract_diff_sanitized(g["text"])
            row = {"id": cid, "issue": t["issue"], "repo": t["repo"], "model": model,
                   "turn": turn, "reply_len": len(g["text"])}
            if not san:
                row.update({"applied": False, "reason": "pas-de-diff-extrable"})
                prev_diff = g["text"][:PREV_DIFF_CHARS]
                prev_fb = "(aucun diff extrable de votre réponse précédente)"
            else:
                (tdir / f"t{turn}.diff").write_text(san + "\n")
                tmp = Path(f"/tmp/rp-{sha256(cid.encode()).hexdigest()[:8]}.diff")
                tmp.write_text(san + "\n")
                subprocess.run(["scp", "-q", str(tmp), f"{rth.HOST}:/tmp/rp-{sha256(cid.encode()).hexdigest()[:8]}.diff"],
                               capture_output=True, check=False, timeout=120)
                tmp.unlink(missing_ok=True)
                rf = f"/tmp/rp-{sha256(cid.encode()).hexdigest()[:8]}.diff"
                sha_pre = {f: rth.run(f"sha256sum {wt}/{f} | cut -c1-16").strip() for f in t["src_files"]}
                err_apply = rth.run(f"cd {wt} && git apply --recount {rf} 2>&1")
                err_apply2 = ""
                applied = any(sha_pre[f] != rth.run(f"sha256sum {wt}/{f} | cut -c1-16").strip() for f in sha_pre)
                if not applied:
                    err_apply2 = rth.run(f"cd {wt} && patch -p1 -l --fuzz=3 < {rf} 2>&1")
                    applied = any(sha_pre[f] != rth.run(f"sha256sum {wt}/{f} | cut -c1-16").strip() for f in sha_pre)
                row["applied"] = applied
                if applied:
                    raw, failed, passed = run_tests(prof, wt, t)
                    f2p_red = sorted(set(t["f2p"]) & set(failed))
                    p2p_broken = [x for x in failed if x not in set(t["f2p"])]
                    row.update({"f2p_red": f2p_red[:8], "p2p_failed": p2p_broken[:6],
                                "n_passed": passed, "failed_all": failed[:40],
                                "y": 1 if (not f2p_red and not p2p_broken) else 0})
                    prev_fb = failure_feedback(raw, failed, f2p_red, p2p_broken)
                    prev_diff = san
                else:
                    prev_fb = ("(le diff n'a PAS pu être appliqué. Sorties réelles :\n"
                               f"git apply: {err_apply[-300:]}\n"
                               f"patch --fuzz=3: {err_apply2[-300:]})\n"
                               "Corrigez les chemins/le contexte EXACTEMENT comme dans les fichiers fournis.")
                    prev_diff = san
                rth.run(f"cd {wt} && git checkout -- . && rm -f {rf}", t=120)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  {cid} applied={row.get('applied')} y={row.get('y')}", flush=True)
            if row.get("y") == 1:
                break
    finally:
        rth.run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null; git worktree prune 2>/dev/null", t=120)


def main() -> int:
    want = os.environ.get("GEN_MODELS", "pro,qwen").split(",")
    models = [(k, MODELS[k.strip()]) for k in want if k.strip() in MODELS]
    sel = json.loads(SELECTION.read_text())["tickets"] if SELECTION.is_file() else select_tickets()
    deja = set()
    if ROWS.is_file():
        for l in ROWS.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                deja.add((r.get("issue"), r.get("model")))
    print(f"REPLAY v28 : {len(sel)} tickets × modèles {[k for k, _ in models]} "
          f"| budget {budget()}/{CAP_TOTAL} | déjà joués {len(deja)}", flush=True)
    with ROWS.open("a") as fh:
        for k, mname in models:
            for t in sel:
                if budget() >= CAP_TOTAL or budget_model(mname) >= CAP_MODEL:
                    break
                if (t["issue"], mname) in deja:
                    continue
                print(f"[{k}] {t['issue']} ({len(t['f2p'])} F2P)", flush=True)
                replay_ticket(t, k, mname, fh)
                deja.add((t["issue"], mname))
    print("REPLAY V28 DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
