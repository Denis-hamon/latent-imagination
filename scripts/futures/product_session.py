#!/usr/bin/env python3
"""v43 — session produit réelle : boucle de réparation qui CONSOMME les deux
colonnes servies (predicted_failing_tests + predicted_evolution) et grounde
chaque issue via report_outcome. Ticket cible : un vérifié MSWB non joué.

Usage: LI_GALERE_MODEL=Qwen3.8-2.4T-A95B-NVFP4 uv run python scripts/futures/product_session.py [--max-turns 3]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NH = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest"
MSWB = ROOT / "data" / "landing" / "act2-pilot" / "mswb"
URL = os.environ.get("GHOST_MCP_URL", "http://51.210.228.117:8093/mcp")

_spec = importlib.util.spec_from_file_location("rth", ROOT / "scripts" / "act2" / "real_ticket_harvest.py")
rth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rth)
_spec2 = importlib.util.spec_from_file_location("mv", ROOT / "scripts" / "act2" / "mswb_verify.py")
mv = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(mv)


def mcp_call(method: str, args: dict) -> dict:
    import urllib.request

    def post(payload: dict, sid: str | None = None) -> tuple[dict, str | None]:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(URL, data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Accept": "application/json, text/event-stream",
                                              **({"Mcp-Session-Id": sid} if sid else {})})
        with urllib.request.urlopen(req, timeout=300) as resp:
            sid2 = resp.headers.get("Mcp-Session-Id") or sid
            txt = resp.read().decode()
        if "\ndata:" in txt or txt.startswith("event:"):
            for line in txt.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:]), sid2
        return (json.loads(txt) if txt else {}), sid2

    init, sid = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "product-session", "version": "1"}}})
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    r2, _ = post({"jsonrpc": "2.0", "id": 2, "method": method,
                  "params": {"name": args.pop("__tool"), "arguments": args}}, sid)
    if "error" in r2:
        raise RuntimeError(str(r2["error"])[:300])
    txt = r2["result"]["content"][0]["text"]
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return {"_raw": txt}


def solve(prompt: str, model: str) -> str:
    rth.MODEL["m"] = model
    g = rth.call_t07(prompt)
    return g["text"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", default="vuejs__core-11026")
    ap.add_argument("--max-turns", type=int, default=3)
    args = ap.parse_args()
    model = os.environ.get("LI_GALERE_MODEL", "Qwen3.8-2.4T-A95B-NVFP4")
    repo = "vuejs__core"
    prof = mv.PROFILES[repo]
    t = next(x for x in json.loads((MSWB / repo / "verified-mswb.json").read_text())
             if x["issue"] == args.ticket)
    wt = f"{prof['wt_root']}/prod-{abs(hash((args.ticket, model))) % 10**8}"
    log = []
    rth.run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null; "
            f"git worktree add {wt} {t['parent']} >/dev/null 2>&1 && "
            + prof["link_nm"].format(wt=wt))
    mv.apply_file(wt, t["test_path"] if "test_path" in t else t["test_patch"], "tp")
    srcs = {f: rth.run(f"cat {wt}/{f} 2>/dev/null | head -900") for f in t["src_files"]}
    declared = sorted(set(t["f2p"]))
    known_red: list[str] = []
    resolved = False
    for turn in range(1, args.max_turns + 1):
        prompt = ("Keep your reasoning SHORT (under 5000 tokens). Then respond with ONLY a "
                  "single ```diff block.\n\n"
                  f"REAL TICKET ({repo} issue {t['issue']}): {t.get('ticket_text','')[:600]}\n\n"
                  "FAILING TESTS (must pass after a correct fix):\n"
                  + "\n".join(f"- {f}" for f in declared)
                  + ("\n\nCURRENTLY STILL FAILING (measured): " + "; ".join(known_red[:10]) if known_red else "")
                  + "\n\nSOURCE FILES (current state):\n"
                  + "\n".join(f"\nFILE {p}:\n```\n{c}\n```" for p, c in srcs.items())
                  + "\n\nMinimal fix, unified diff, git-apply compatible.")
        reply = solve(prompt, model)
        san = rth.PRX.extract_diff_sanitized(reply)
        entry = {"turn": turn, "model": model, "reply_len": len(reply),
                 "diff_extrait": bool(san)}
        if not san:
            entry.update({"status": "pas-de-diff"})
            log.append(entry)
            continue
        # appel serveur : risk_scan (call_id flywheel) puis compare_patches avec colonnes
        diff_short = san[:6000]
        state = t.get("ticket_text", "")[:1200] + "\n" + "; ".join(declared[:6])
        rs = mcp_call("tools/call", {"__tool": "risk_scan",
                                     "state_text": state, "diff_text": diff_short,
                                     "exclude_task": args.ticket,
                                     "reporter": f"product-session/{args.ticket}"})
        cp = mcp_call("tools/call", {"__tool": "compare_patches",
                                     "candidates": [{"id": f"t{turn}", "state_text": state,
                                                     "diff_text": diff_short}],
                                     "budget_n": 8, "declared_tests": declared,
                                     "known_red_tests": known_red, "evolution_turn": turn + 1,
                                     "reporter": f"product-session/{args.ticket}"})
        pft = cp.get("predicted_failing_tests", {}).get(f"t{turn}", {})
        pev = cp.get("predicted_evolution", {}).get(f"t{turn}", {})
        entry["risk_scan"] = rs.get("decision")
        entry["call_id"] = rs.get("call_id")
        entry["pft"] = {x["test"][:50]: x["p_failing"] for x in pft.get("tests", [])}
        entry["pev"] = {x["test"][:50]: x["p_still_red"] for x in pev.get("tests", [])} if pev.get("status") == "measured" else pev.get("status")
        # pose + exécution RÉELLE
        sha_pre = {f: rth.run(f"sha256sum {wt}/{f} | cut -c1-16").strip() for f in t["src_files"]}
        mv.apply_file(wt, san, f"t{turn}")
        applied = any(sha_pre[f] != rth.run(f"sha256sum {wt}/{f} | cut -c1-16").strip() for f in sha_pre)
        entry["applied"] = applied
        if applied:
            tests = " ".join(t["tests_run"])
            raw = rth.run(prof["cmd"].format(wt=wt, tests=tests, names=""), t=420)
            failed, passed = rth.parse_leaves(raw, prof["runner"])
            fname = {mv.norm(x) for x in failed}
            f2p_norm = {mv.norm(x) for x in declared}
            red = sorted({x for x in f2p_norm if any(x == f or f.startswith(x) or x.startswith(f) for f in fname)})
            p2p_brok = sorted({f for f in fname if f not in f2p_norm})
            y = 1 if not red and not p2p_brok else 0
            known_red = red
            entry.update({"y": y, "f2p_rouges": red, "p2p_casses": p2p_brok[:4], "n_passed": passed})
            # prédiction vs réalité (évolution)
            pred = {x["test"]: x for x in pev.get("tests", [])}
            if pev.get("status") == "measured" and pred:
                hit = []
                for test in declared:
                    pt = pred.get(test) or next((v for k, v in pred.items() if test.endswith(k) or k.endswith(test)), None)
                    if pt:
                        hit.append((test[:40], pt["predicted_red"], test.lower() in [r.lower() for r in red] or mv.norm(test) in red))
                entry["pev_vs_reel"] = hit
            # grounde l'issue via report_outcome (flywheel)
            if rs.get("call_id"):
                try:
                    mcp_call("tools/call", {"__tool": "report_outcome", "call_id": rs["call_id"],
                                            "passed": bool(y), "reporter": f"product-session/{args.ticket}",
                                            "grounded_by": "vitest"})
                    entry["report_outcome"] = "ok"
                except Exception as e:  # noqa: BLE001
                    entry["report_outcome"] = f"err {str(e)[:80]}"
            if y == 1:
                resolved = True
                log.append(entry)
                break
        log.append(entry)
        srcs = {f: rth.run(f"cat {wt}/{f} 2>/dev/null | head -900") for f in t["src_files"]}
    rth.run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null", t=180)
    out = {"ticket": args.ticket, "model": model, "r\u00e9solu": resolved, "tours": len(log), "log": log}
    f = MSWB / f"product-session-{args.ticket}.json"
    f.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({"ticket": args.ticket, "r\u00e9solu": resolved, "tours": len(log)}, ensure_ascii=False))
    for e in log:
        print(f"  tour {e['turn']}: risk={e.get('risk_scan')} appl={e.get('applied')} y={e.get('y')}")
    return 0 if resolved else 1


if __name__ == "__main__":
    sys.exit(main())
