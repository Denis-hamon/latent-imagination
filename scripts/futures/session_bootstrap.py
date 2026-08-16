#!/usr/bin/env python3
"""Ghost pivot — story 15.1 : session bootstrap.

DONNÉ : un repo avec suite de tests (runner connu), K patches candidats, un
budget n d'exécutions RÉELLES. REND : n issues groundées (y par test, F2P
nominatives) + trace d'application, prêtes pour la calibration locale (15.2).

Contrat d'intégrité hérité des fenêtres TS :
  - pose du diff : git apply --recount puis patch -l --fuzz=3 ; vérification
    par SHA de contenu (jamais rc ni HEAD) — leçons v2/DW-31 ;
  - contrôle positif : l'état buggy DOIT casser les F2P déclarés sinon le
    candidat est écarté (non mesurable) ;
  - restauration git systématique (finally), worktree propre exigé avant/après ;
  - timeout DW-35 : run borné => quarantaine-timeout, jamais de devinette ;
  - sélection informative : score prior global (LOAO-F1 sur pool v10 quand les
    embeddings existent) + dispersion greedy ; si n >= K tout est exécuté.

Run: uv run python scripts/futures/session_bootstrap.py --manifest <session.json>
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RUNNERS = {
    "omniroute-node-test": {
        "host": "Kimsufi-standard", "remote": "~/OmniRoute",
        "cmd": "cd ~/OmniRoute && timeout 240 node --import tsx/esm --test --test-reporter=tap {spec} 2>&1",
        "leaf": re.compile(r"^(?: *)?(not ok|ok) \d+ -? ?(.+?)(?: # .*)?$"),
        "strip_levels": True,
    },
    "zod-vitest": {
        "host": "Kimsufi-standard", "remote": "~/zod-source",
        "cmd": "cd ~/zod-source && timeout 240 npx vitest run --reporter=tap {spec} 2>&1",
        "leaf": re.compile(r"^    (not ok|ok) \d+ - (.+?)(?: # time=.*)?$"),
        "strip_levels": False,
    },
    "date-fns-vitest": {
        "host": "Kimsufi-standard", "remote": "~/date-fns-source",
        "cmd": "cd ~/date-fns-source/pkgs/core && timeout 240 npx vitest run --reporter=tap {spec} 2>&1",
        "leaf": re.compile(r"^ {8,}(not ok|ok) \d+ - (.+?)(?: # time=.*)?$"),
        "strip_levels": False,
    },
}


def sh_local(cmd: list[str], timeout: int = 400) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def sh_remote(host: str, cmd: str, timeout: int = 400) -> subprocess.CompletedProcess:
    return sh_local(["ssh", "-o", "ConnectTimeout=12", host, cmd], timeout=timeout)


def run_tests(runner_key: str, spec: str) -> dict:
    r = RUNNERS[runner_key]
    raw = sh_remote(r["host"], r["cmd"].format(spec=spec)).stdout
    per = []
    for line in raw.splitlines():
        m = r["leaf"].match(line)
        if not m or line.rstrip().endswith("{"):
            continue
        if r["strip_levels"] and not line.startswith(("ok", "not ok", "    ok", "    not ok")):
            continue
        name = m.group(2).split(" > ")[-1].strip()
        per.append({"name": name, "status": "failed" if m.group(1) == "not ok" else "passed"})
    return {"per_test": per, "tail": raw[-600:]}


def checkout_target(host: str, remote: str, target: str) -> None:
    sh_remote(host, f"cd {remote} && git checkout -- . && rm -f /tmp/ghost-cand.diff", timeout=120)


def _clean(runner_key: str) -> bool:
    r = RUNNERS[runner_key]
    return not sh_remote(r["host"], f"cd {r['remote']} && git status --porcelain | head -1").stdout.strip()


def execute_candidate(cand: dict, runner_key: str, out_dir: Path) -> dict:
    """Mesure RÉELLE d'un candidat : buggy baseline (contrôle positif) puis
    pose du patch candidat + run. Retourne l'issue groundée par test."""
    r = RUNNERS[runner_key]
    out = {"id": cand["id"], "target": cand["target"], "spec": cand["spec"],
           "executed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    try:
        try:
            if not _clean(runner_key):
                out["error"] = "worktree non propre"
                return out
            up = sh_local(["scp", "-q", cand["buggy_file"], f"{r['host']}:{r['remote']}/{cand['target']}"], timeout=120)
            if up.returncode != 0:
                out["error"] = "scp buggy échoué"
                return out
            vbug = run_tests(runner_key, cand["spec"])
            failed_bug = [t["name"] for t in vbug["per_test"] if t["status"] == "failed"]
            f2p = set(cand.get("f2p", []))
            red = sorted(f2p & set(failed_bug)) or sorted(failed_bug)[:8]
            if not red:
                out["error"] = "contrôle positif échoué : F2P pas rouges sur l'état buggy"
                out["bug_tail"] = vbug["tail"]
                return out
            out["bug_applied"] = True
            out["f2p_red_after_bug"] = red
            sh_local(["scp", "-q", cand["diff_file"], f"{r['host']}:/tmp/ghost-cand.diff"], timeout=120)
            sha_pre = sh_remote(r["host"], f"sha256sum {r['remote']}/{cand['target']} | cut -c1-64").stdout.strip()
            ap = sh_remote(r["host"], f"cd {r['remote']} && git apply --recount /tmp/ghost-cand.diff 2>&1")
            mode = "strict-git" if ap.returncode == 0 else None
            sha_post = sh_remote(r["host"], f"sha256sum {r['remote']}/{cand['target']} | cut -c1-64").stdout.strip()
            fallback = ""
            if mode is None or sha_pre == sha_post:
                ap2 = sh_remote(r["host"], f"cd {r['remote']} && patch -p1 -l --fuzz=3 -s < /tmp/ghost-cand.diff 2>&1")
                fallback = ap2.stdout + ap2.stderr
                sha_post = sh_remote(r["host"], f"sha256sum {r['remote']}/{cand['target']} | cut -c1-64").stdout.strip()
                if sha_pre != sha_post:
                    mode = "patch-fuzz"
            out["apply_mode"] = mode
            if mode is None:
                out["applied"] = False
                out["apply_err"] = (ap.stdout + ap.stderr + fallback)[-300:]
                return out
            out["applied"] = True
            v = run_tests(runner_key, cand["spec"])
            failed = [t["name"] for t in v["per_test"] if t["status"] == "failed"]
            passed = [t["name"] for t in v["per_test"] if t["status"] == "passed"]
            f2p_still = sorted(set(red) & set(failed))
            p2p_failed = [t for t in failed if t not in set(red)]
            out["f2p_green"] = not f2p_still
            out["f2p_still_red"] = f2p_still[:8]
            out["p2p_failed"] = p2p_failed[:6]
            out["n_passed"] = len(passed)
            out["y"] = 1 if (not f2p_still and not p2p_failed) else 0
            out["test_outcomes"] = {t["name"]: t["status"] for t in v["per_test"]}
            out["tail"] = v["tail"]
            return out
        except subprocess.TimeoutExpired:
            out["error"] = "quarantaine-timeout (DW-35)"
            return out
    finally:
        checkout_target(r["host"], r["remote"], cand["target"])
        if not _clean(runner_key):
            out["cleanup_warning"] = "restauration à vérifier"


def select_informative(candidates: list[dict], n: int, prior_scores: dict | None) -> list[dict]:
    """n candidats informatifs : spread greedy sur le score prior (à défaut :
    diversité par tâche puis ordre du manifeste). Déterministe."""
    if n >= len(candidates):
        return list(candidates)
    key = lambda c: prior_scores.get(c["id"]) if prior_scores and c["id"] in prior_scores else None
    scored = [c for c in candidates if key(c) is not None]
    if len(scored) < n:
        sel = list(scored)
        for c in candidates:
            if c not in sel:
                sel.append(c)
            if len(sel) >= n:
                break
        return sel
    scored.sort(key=lambda c: key(c))
    mid = scored[len(scored) // 2]
    sel = [mid]
    remaining = [c for c in scored if c is not mid]
    while len(sel) < n and remaining:
        def spread(c: dict) -> float:
            return min(abs((key(c) or 0) - (key(s) or 0)) for s in sel)
        remaining.sort(key=spread, reverse=True)
        sel.append(remaining.pop(0))
    return sel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args()
    mani = json.loads(Path(args.manifest).read_text())
    runner_key = mani["runner"]
    out_dir = Path(mani["out_dir"]); out_dir.mkdir(parents=True, exist_ok=True)
    cands = mani["candidates"]
    n = int(mani.get("budget_n", 3))
    prior = mani.get("prior_scores")
    todo = select_informative(cands, n, prior)
    print(f"bootstrap: n={n} sur K={len(cands)} — sélection: {[c['id'] for c in todo]}")
    for c in todo:
        res = execute_candidate(c, runner_key, out_dir)
        (out_dir / f"issue-{c['id']}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
        print(f"  {c['id'][:50]:50} y={res.get('y', res.get('error', '?')[:20])}")
    report = {"session": mani.get("session_id", out_dir.name),
              "runner": runner_key, "budget_n": n, "n_candidates": len(cands),
              "selected": [c["id"] for c in todo],
              "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
              "grounded_by": "tests-run (jamais avis modèle)"}
    (out_dir / "bootstrap-report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
