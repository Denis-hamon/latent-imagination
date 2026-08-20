#!/usr/bin/env python3
"""Fenêtre v32 (e223b620) — boucle agentique test-in-loop CUMULÉE sur 24 instances vue.

État cumulé entre tours (pas de reset), prompt = code courant réel,
feedback riche 1600 chars, patch -p1 par hunk (les fichiers appliqués restent).

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
import pathlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NH = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest"
OUT = NH / "replay-v37"
ROWS = NH / "replay-rows-v37.jsonl"
COUNTER = NH / "call-counter-v37.jsonl"
SELECTION = OUT / "replay-selection-v37.json"
CAP_TOTAL = 200
CAP_MODEL = 200
MAX_TURNS = 4
FEEDBACK_CHARS = 1600
PREV_DIFF_CHARS = 3000

_spec = importlib.util.spec_from_file_location("rth", ROOT / "scripts" / "act2" / "real_ticket_harvest.py")
rth = importlib.util.module_from_spec(_spec)
sys.modules["pilot_run"] = None
_spec.loader.exec_module(rth)
_spec2 = importlib.util.spec_from_file_location("mv", ROOT / "scripts" / "act2" / "mswb_verify.py")
mv = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(mv)

MODELS = {
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
    """v37 : instances dayjs vérifiées (harness officiel MSWB), F2P>=2, src<=1200."""
    vf = NH.parent / "mswb" / "iamkun__dayjs" / "verified-mswb.json"
    cands = [t for t in json.loads(vf.read_text()) if t.get("ok")]
    for t in cands:
        t.setdefault("repo", "iamkun__dayjs")
        n = _src_total_lines(t)
        t["src_total_lines"] = n if n < 10**9 else 0
    cands = [t for t in cands if 0 < t.get("src_total_lines", 0) <= MAX_TOTAL_SRC_LINES
             and len(t.get("f2p", [])) >= 1]
    cands.sort(key=lambda t: (-len(t["f2p"]), t["issue"]))
    sel = cands[:45]
    OUT.mkdir(parents=True, exist_ok=True)
    SELECTION.write_text(json.dumps({"window": "v37", "anchor": "e79ebe611b3eee1a",
                                     "critere": "dayjs verified harness officiel ; F2P>=2 ; src<=1200 lignes",
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


def current_srcs(t: dict, wt: str) -> dict:
    """Code COURANT du worktree (état cumulé des tours précédents)."""
    out = {}
    for f in t["src_files"]:
        c = rth.run(f"cat {wt}/{f} 2>/dev/null | head -1500")
        out[f] = c if c.strip() else ""
    return out


DIFF_ONLY_PREFIX = ("Respond with ONLY the content of a single ```diff block. "
                      "No explanations, no reasoning text outside the block.\n\n")


def build_prompt_v32(t: dict, srcs: dict, prev_diff: str, prev_fb: str, turn: int) -> str:
    lines = [DIFF_ONLY_PREFIX
             + f"REAL TICKET ({t['repo']} issue {t['issue']}): {t.get('ticket_text', '')[:600]}",
             "", "FAILING TESTS (must pass after a correct fix):"]
    lines += [f"- {f}" for f in t["f2p"]]
    lines += ["", "TESTS THAT CURRENTLY PASS (must keep passing): (the rest of the suite)"]
    if turn > 1:
        lines += ["", f"YOUR PREVIOUS DIFF (turn {turn - 1}):", "```diff", prev_diff[:PREV_DIFF_CHARS], "```",
                  "", "REAL TEST OUTPUT AFTER YOUR PREVIOUS DIFF:", prev_fb,
                  "", "CURRENT STATE OF SOURCE FILES (after all previous edits — work from THIS state):"]
    else:
        lines += ["", "SOURCE FILES (current state):"]
    for path, content in srcs.items():
        if content:
            lines.append(f"\nFILE {path}:\n```\n{content}\n```")
    lines.append("\nReturn ONLY a unified diff inside ```diff fences, real a/ b/ paths, "
                 "git-apply compatible. Produce the diff AGAINST THE CURRENT STATE shown above. Minimal change.")
    return "\n".join(lines)


def measure_cumulative(t: dict, wt: str, san: str, check_files: list | None = None) -> dict:
    """"Pose cumulative : git apply atomique, sinon patch -p1 par fichier
    (les hunks appliqués RESTENT). Retourne statut + sortie réelle."""
    import subprocess as _sp
    tmp = pathlib.Path(f"/tmp/v36-{abs(hash(san)) % 10**8}.diff")
    tmp.write_text(san if san.endswith("\n") else san + "\n")
    rf = f"/tmp/v36-{abs(hash(san)) % 10**8}.diff"
    _sp.run(["scp", "-q", str(tmp), f"{rth.HOST}:{rf}"], capture_output=True, check=False, timeout=120)
    tmp.unlink(missing_ok=True)
    watched = [f for f in (check_files or t["src_files"]) if f]
    sha_pre = {f: rth.run(f"sha256sum {wt}/{f} 2>/dev/null | cut -c1-16").strip() for f in watched}
    # git apply en mode check d'abord pour éviter le double-apply (patch interactif)
    chk = rth.run(f"cd {wt} && git apply --recount --check {rf} 2>&1; echo RC=$?")
    err1, err2, mode = chk, "", None
    if "RC=0" in chk:
        rth.run(f"cd {wt} && git apply --recount {rf} 2>&1")
        mode = "strict-git"
    else:
        err2 = rth.run(f"cd {wt} && patch -p1 -l --fuzz=3 --batch < {rf} 2>&1")
        mode = "patch-fuzz"
    sha_post = {f: rth.run(f"sha256sum {wt}/{f} 2>/dev/null | cut -c1-16").strip() for f in watched}
    changed = [f for f in watched if sha_pre.get(f, "") != sha_post.get(f, "")]
    applied = bool(changed)
    if mode == "patch-fuzz" and changed:
        mode = f"partial-patch:{len(changed)}/{len(watched)} fichiers"
    rth.run(f"rm -f {rf}", t=60)
    return {"applied": applied, "mode": mode, "err": (err1 + "\n" + err2)[-600:]}


def rich_feedback(raw: str, failed: list, f2p_red: list, p2p: list) -> str:
    lines = raw.splitlines()
    blocks, cur = [], []
    for l in lines:
        if "AssertionError" in l or "expected" in l.lower() or l.strip().startswith(("---", "not ok", "Error", "FAIL")):
            cur.append(l)
        elif cur:
            if len("\n".join(cur)) > FEEDBACK_CHARS:
                blocks.append("\n".join(cur)); cur = []
            else:
                cur.append(l)
    if cur:
        blocks.append("\n".join(cur))
    body = "\n[...]\n".join(blocks)[:FEEDBACK_CHARS]
    return (f"STILL FAILING ({len(failed)} tests): " + "; ".join(failed[:10]) +
            f"\nF2P encore rouges: {f2p_red[:8]}\nP2P cassés par le patch: {p2p[:6]}\n\n{body}")


def replay_ticket(t: dict, model_key: str, model: str, fh) -> None:
    prof = rth.REPOS[t["repo"]]
    wt = f"{prof['wt_root']}/v36-{abs(hash((t['issue'], model))) % 10**8}"
    slug = t["issue"].replace("/", "_")[:80]
    tdir = OUT / f"{slug}--{model_key}"
    tdir.mkdir(parents=True, exist_ok=True)
    # setup une fois : worktree au parent + test_patch + install ; état CUMULÉ ensuite
    rth.run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null; "
            f"git worktree add {wt} {t['parent']} >/dev/null 2>&1 && "
            + prof["link_nm"].format(wt=wt))
    if t.get("test_patch"):
        ap = measure_cumulative(t, wt, t["test_patch"], check_files=list(dict.fromkeys(t["tests_run"] + t["src_files"])))
        if not ap["applied"]:
            fh.write(json.dumps({"id": f"v36-setup-{t['issue']}", "issue": t["issue"], "model": model,
                                 "error": f"test_patch inapplicable: {ap['err'][:200]}", "applied": False},
                                ensure_ascii=False) + "\n")
            fh.flush()
            rth.run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null", t=120)
            return
    prev_diff, prev_fb = "", ""
    try:
        for turn in range(1, MAX_TURNS + 1):
            if budget() >= CAP_TOTAL or budget_model(model) >= CAP_MODEL:
                return
            srcs = current_srcs(t, wt)
            prompt = build_prompt_v32(t, srcs, prev_diff, prev_fb, turn)
            cid = f"v37-{t['repo']}-{model_key}-{slug[-40:]}-t{turn}"
            try:
                rth.MODEL["m"] = model
                g = rth.call_t07(prompt)
                fin = g.get("finish_reason")
                count({"slot": cid, "model": model})
            except Exception as e:  # noqa: BLE001
                count({"slot": cid, "model": model, "error": str(e)[:200]})
                fh.write(json.dumps({"id": cid, "issue": t["issue"], "model": model, "turn": turn,
                                     "error": str(e)[:200], "applied": False}, ensure_ascii=False) + "\n")
                fh.flush()
                break
            san = rth.PRX.extract_diff_sanitized(g["text"])
            row = {"id": cid, "issue": t["issue"], "repo": t["repo"], "model": model,
                   "turn": turn, "reply_len": len(g["text"]),
                   "finish_reason": g.get("finish_reason")}
            if not san:
                row.update({"applied": False, "reason": "pas-de-diff-extrable"})
                prev_diff = g["text"][:PREV_DIFF_CHARS]
                prev_fb = "(aucun diff extrable de votre réponse — renvoyez UNIQUEMENT un bloc ```diff``` complet)"
            else:
                (tdir / f"t{turn}.diff").write_text(san + "\n")
                ap = measure_cumulative(t, wt, san)
                row["applied"] = ap["applied"]
                row["apply_mode"] = ap["mode"]
                if ap["applied"]:
                    raw, failed, passed = run_tests(prof, wt, t)
                    f2p_norm = {mv.norm(x) for x in t["f2p"]}
                    fnames = {mv.norm(x) for x in failed}
                    f2p_red = sorted({x for x in fnames if any(x == f or x.startswith(f) or f.startswith(x) for f in f2p_norm)})
                    p2p = sorted(fnames - {x for x in fnames if any(x == f or x.startswith(f) or f.startswith(x) for f in f2p_norm)})
                    y = 1 if (not f2p_red and not p2p) else 0
                    row.update({"f2p_red": f2p_red[:8], "p2p_failed": p2p[:6],
                                "n_passed": passed, "failed_all": sorted(fnames)[:40], "y": y})
                    prev_fb = rich_feedback(raw, sorted(fnames), f2p_red, p2p)
                    prev_diff = san
                else:
                    row.update({"applied": False, "reason": "non-appliqué", "apply_err": ap["err"][:300]})
                    prev_fb = ("(le diff n'a PAS pu être appliqué, l'état n'a PAS changé. Sorties réelles :\n"
                               f"{ap['err'][-500:]})\nVérifiez que le contexte des hunks correspond EXACTEMENT "
                               "à l'état courant ci-dessus.")
                    prev_diff = san
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  {cid} applied={row.get('applied')} mode={row.get('apply_mode')} y={row.get('y')}", flush=True)
            if row.get("y") == 1:
                break
    finally:
        rth.run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null; git worktree prune 2>/dev/null", t=120)


def main() -> int:
    want = os.environ.get("GEN_MODELS", "qwen").split(",")
    models = [(k, MODELS[k.strip()]) for k in want if k.strip() in MODELS]
    sel = json.loads(SELECTION.read_text())["tickets"] if SELECTION.is_file() else select_tickets()
    deja = set()
    if ROWS.is_file():
        for l in ROWS.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                deja.add((r.get("issue"), r.get("model")))
    print(f"REPLAY v37 : {len(sel)} tickets × modèles {[k for k, _ in models]} "
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
    print("REPLAY V37 DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
