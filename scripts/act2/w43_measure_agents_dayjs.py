#!/usr/bin/env python3
"""Fenêtre v30 (498870c8) — mesure des patchs d'agents Multi-SWE-bench sur les
24 instances vue vérifiées. 1 worktree/install par instance, N patchs d'agents
mesurés dedans (git checkout -- . entre chaque). Zéro appel LLM.
Run: uv run python scripts/act2/v30_measure_agents.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
MSWB = PILOT / "mswb" / "iamkun__dayjs"
OUT = MSWB / "agent-measured.json"

_spec = importlib.util.spec_from_file_location(
    "mv", ROOT / "scripts" / "act2" / "mswb_verify.py")
mv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mv)
prof = mv.PROFILES["iamkun__dayjs"]
run = mv.run
HOST = "Kimsufi-standard"


def apply_patch_file(wt: str, patch: str, tag: str) -> str:
    """Pose d'un patch via fichier scp (jamais heredoc ssh : ARG_MAX)."""
    h = sha256((tag + patch).encode()).hexdigest()[:10]
    tmp = Path(f"/tmp/w43-{tag}-{h}.diff")
    tmp.write_text(patch if patch.endswith("\n") else patch + "\n")
    rf = f"/tmp/w43-{tag}-{h}.diff"
    subprocess.run(["scp", "-q", str(tmp), f"{HOST}:{rf}"],
                   capture_output=True, check=False, timeout=120)
    tmp.unlink(missing_ok=True)
    out = run(f"cd {wt} && (git apply --recount {rf} 2>&1) || "
              f"(patch -p1 -l --fuzz=3 < {rf} 2>&1); rm -f {rf}")
    return out


def norm_name(x: str) -> str:
    x = x.split(" # ")[0].strip()
    return re.sub(r"^\d+ - ", "", x).strip()


def main() -> int:
    sel = json.loads((MSWB / "agent-patches-selection.json").read_text())
    verified = json.loads((MSWB / "verified-mswb.json").read_text())
    t_by = {t["issue"]: t for t in verified}
    for p_ in sel:
        p_.setdefault("model", p_.get("model", "?"))
    by_inst: dict[str, list] = {}
    for p in sel:
        by_inst.setdefault(p["instance"], []).append(p)
    done = []
    if OUT.is_file():
        done = json.loads(OUT.read_text())
    done_keys = {(d["instance"], d["patch_sha"]) for d in done}
    for i, (inst, patches) in enumerate(sorted(by_inst.items())):
        todo = [p for p in patches if (inst, p["patch_sha"]) not in done_keys]
        if not todo:
            continue
        t = t_by[inst]
        print(f"[{i+1}/{len(by_inst)}] {inst} ({len(todo)} patchs à mesurer)", flush=True)
        wt = f"{prof['wt_root']}/w43-{abs(hash(inst)) % 10**8}"
        run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null; "
            f"git worktree add {wt} {t['parent']} >/dev/null 2>&1")
        run(prof["link_nm"].format(wt=wt))
        apply_patch_file(wt, t["test_patch"], f"test-{abs(hash(inst)) % 10**6}")
        tests = " ".join(t["tests_run"][:6])
        f2p = {mv.norm(x) for x in t["f2p"]}
        for p in todo:
            ap = apply_patch_file(wt, p["patch"], p["patch_sha"])
            raw = run(prof["cmd"].format(wt=wt, tests=tests, names=""))
            failed, passed = mv.rth.parse_leaves(raw, prof["runner"])
            fnames = {norm_name(x) for x in failed}
            still_red = {x for x in f2p if any(x == f or f.startswith(x) or x.startswith(f) for f in fnames)}
            p2p_brok = {f for f in fnames if not any(f == x or f.startswith(x) or x.startswith(f) for x in f2p)}
            applied = "patch does not apply" not in ap and "FAILED" not in ap
            row = {"instance": inst, "patch_sha": p["patch_sha"], "agent": p["agent"],
                   "model": p["model"], "applied": applied,
                   "y": 1 if (applied and not still_red and not p2p_brok) else 0,
                   "n_still_red": len(still_red), "n_f2p": len(f2p),
                   "failed_all": sorted(fnames)[:40], "n_passed": passed,
                   "measured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
            done.append(row)
            run(f"cd {wt} && git checkout -- . ", t=120)
            print(f"  {p['model'][:24]:26} appl={applied} y={row['y']} "
                  f"({len(f2p)-len(still_red)}/{len(f2p)} réparés)", flush=True)
        OUT.write_text(json.dumps(done, indent=1, ensure_ascii=False) + "\n")
        run(f"cd {prof['remote']} && git worktree remove --force {wt} 2>/dev/null", t=120)
    y1 = sum(1 for d in done if d["y"] == 1)
    app = [d for d in done if d["applied"]]
    part_nt = [d for d in app if d["y"] == 0 and d["n_still_red"] < d["n_f2p"]]
    print(json.dumps({"total": len(done), "appliques": len(app), "y1": y1,
                      "partielles_non_triviales": len(part_nt)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
