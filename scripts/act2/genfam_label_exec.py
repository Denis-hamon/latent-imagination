#!/usr/bin/env python3
"""Story 10.2 — exécution docker de la chaîne stricte de labellisation genfam (NODE).

Protocole IDENTIQUE à s12_label_exec / pilot_node_exec (chaîne stricte, sans
juge) : image swe-smith de la tâche → apply bug-inducteur (staging patch) →
apply diff candidat (strict, git apply) → py_compile target → pytest F2P
(-x -q, 4 premiers) → P2P (20 premiers, seulement si F2P vert et déclarés).

Sortie = PREUVE BRUTE par slot : gen-results/<slot>/run-result.json
(booleens de chaîne + tails raw des pytest). La classification en labels est
un acte séparé, offline, par rules_v1 uniquement (genfam_label_build.py) —
les labels restent re-dérivables des raw traces (FR-3).

Idempotent : run-result.json existant = skip (batch 1 maintenant, les slots
retardataires de Q1 seront labellisés au batch 2 sans re-mesure du batch 1).

Run (node): python3 scripts/act2/genfam_label_exec.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot")
Q = BASE / "genfam-q1"
RESULTS = Q / "gen-results"
STAGING = Q / "staging-extract.json"
PY = "/opt/miniconda3/envs/testbed/bin/python"


def sh(cmd: list[str], timeout: int = 1200) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def run_slot(slot_dir: Path, staging_by_iid: dict) -> dict:
    rec = json.loads((slot_dir / "rec.json").read_text())
    iid = rec["task"]
    st = staging_by_iid.get(iid, {})
    out = {"task": iid, "slot": slot_dir.name, "campaign": rec.get("campaign"),
           "window": "gen-families-v1", "author": rec.get("author"),
           "draw": rec.get("draw"), "diff_sha256": rec.get("diff_sha256")}
    patch = slot_dir / "diff.patch"
    if not patch.is_file() or not patch.read_text().strip():
        return dict(out, error="pas de diff.patch")
    if not st.get("image") or not st.get("patch"):
        return dict(out, error="staging incomplet (image/patch)")

    box = f"li-genfam-l-{iid.split('.')[0][:18].replace('/', '_')}-{slot_dir.name[-4:]}"
    sh(["docker", "rm", "-f", box])
    pl = sh(["docker", "pull", st["image"]], timeout=1800)
    if pl.returncode != 0 and "Already exists" not in pl.stderr and "Image is up to date" not in (pl.stdout + pl.stderr):
        return {**out, "error": "docker pull failed", "stderr": pl.stderr[-300:]}
    up = sh(["docker", "run", "-d", "--name", box, st["image"], "sleep", "infinity"])
    if up.returncode != 0:
        return {**out, "error": "docker run failed", "stderr": up.stderr[-300:]}
    try:
        find = sh(["docker", "exec", box, "bash", "-c",
                   "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
        if not find:
            return dict(out, error="repo .git introuvable dans l'image")
        repo = str(Path(find).parent)
        bug = Q / f".tmp-bug-{slot_dir.name[-10:]}.diff"
        bug.write_text(st["patch"])
        sh(["docker", "cp", str(bug), f"{box}:/tmp/bug.diff"])
        sh(["docker", "cp", str(patch), f"{box}:/tmp/patch.diff"])
        bug.unlink(missing_ok=True)

        bg = sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/bug.diff"])
        out["bug_applied"] = bg.returncode == 0
        if not out["bug_applied"]:
            out["bug_apply_err"] = bg.stderr[-300:]
            return out
        ap = sh(["docker", "exec", box, "git", "-C", repo, "apply", "--verbose", "/tmp/patch.diff"])
        out["patch_applied"] = ap.returncode == 0
        if not out["patch_applied"]:
            out["apply_err"] = ap.stderr[-400:]
            return out
        cp = sh(["docker", "exec", box, PY, "-m", "py_compile", f"{repo}/{st['target']}"])
        out["py_compiles"] = cp.returncode == 0
        if cp.returncode != 0:
            out["py_compile_err"] = cp.stderr[-300:]
        f2p = st.get("f2p") or []
        if f2p:
            r = sh(["docker", "exec", box, "bash", "-c",
                    f"cd {repo} && {PY} -m pytest -x -q {' '.join(map(str, f2p[:4]))}"])
            out["f2p_rc"] = r.returncode
            out["f2p_tail"] = (r.stdout + r.stderr)[-800:]
        p2p = st.get("p2p") or []
        if out.get("f2p_rc") == 0 and p2p:
            rp = sh(["docker", "exec", box, "bash", "-c",
                     f"cd {repo} && {PY} -m pytest -q {' '.join(map(str, p2p[:20]))}"])
            out["p2p_rc"] = rp.returncode
            out["p2p_tail"] = (rp.stdout + rp.stderr)[-600:]
        elif out.get("f2p_rc") == 0 and not p2p:
            out["p2p_rc"] = None  # tâche sans P2P déclarés : absents, pas échoués
        return out
    except subprocess.TimeoutExpired:
        return dict(out, error="timeout docker exec")
    finally:
        sh(["docker", "rm", "-f", box], timeout=120)


def main() -> int:
    staging = json.loads(STAGING.read_text())
    by_iid = {t["instance_id"]: t for t in staging["tasks"]}
    slots = []
    for sd in sorted(RESULTS.glob("*-d*")):
        rf = sd / "rec.json"
        if not rf.is_file():
            continue
        if json.loads(rf.read_text()).get("status") == "ok":
            slots.append(sd)
    done = run = errors = 0
    for sd in slots:
        if (sd / "run-result.json").is_file():
            done += 1
            continue
        r = run_slot(sd, by_iid)
        (sd / "run-result.json").write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
        run += 1
        errors += 1 if r.get("error") else 0
        print(f"{sd.name[:52]:52} bug={r.get('bug_applied')} patch={r.get('patch_applied')} "
              f"f2p_rc={r.get('f2p_rc')} p2p_rc={r.get('p2p_rc')}" +
              (f" ERR={r.get('error')}" if r.get("error") else ""), flush=True)
    print(f"\n== GENFAM-L : {done} déjà mesurés, {run} exécutés, {errors} erreurs ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
