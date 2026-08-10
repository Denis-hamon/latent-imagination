#!/usr/bin/env python3
"""S6 — labellisation 0-call des 128 candidats boltzmann-e1 (node WMEL-gpu-strong).

Constat : boltzmann-e1 a persisté 4 diffs × 32 tâches (panel frozen32) mais seuls
2 verdicts ont été exécutés (e1-f2p.json, mapping sélection uniquement). Les 126
autres candidats n'ont JAMAIS été exécutés → labels gratuits, pure exécution
docker, zéro call galere.

Protocole d'exécution STRICTEMENT identique à pilot_node_exec.run_one :
container image swe-smith de la tâche → apply bug gold → apply patch candidat →
py_compile de la cible → pytest F2P (4 premiers) → P2P (pilot-tasks racine)
uniquement si F2P vert. Idempotent : label JSON existant = skip.

Entrées (déjà sur le node) :
  $BASE/boltzmann-out.json        (image, target, f2p, candidates k)
  $BASE/boltzmann-e1/<task>-cand{K}.diff
  $BASE/control-gold/<task>/gold.diff  (le bug à réinjecter)
  $BASE/pilot-tasks-frozen32.json (p2p du panel)
Sortie : $BASE/boltzmann-e1/labels/<task>-cand{K}.json
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

BASE = Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot")
OUT = json.loads((BASE / "boltzmann-out.json").read_text())
LABELS = BASE / "boltzmann-e1" / "labels"
LABELS.mkdir(exist_ok=True)
P2P = {}
pt = BASE / "pilot-tasks-frozen32.json"
if pt.is_file():
    P2P = {t["instance_id"]: t.get("p2p", [])
           for t in json.loads(pt.read_text())}


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def run_cand(entry, k):
    iid = entry["task"]
    tag = f"{iid.replace('/', '_')}-cand{k}"
    lf = LABELS / f"{tag}.json"
    if lf.is_file():
        return None  # idempotent
    diff = BASE / "boltzmann-e1" / f"{tag}.diff"
    if not diff.is_file() or not diff.read_text().strip():
        return {"task": iid, "cand": k, "error": "diff absente/vide"}
    box = f"li-s6-{tag.split('.')[0].replace('/', '_')[:18]}-{k}"
    meta = {"task": iid, "cand": k, "diff_file": diff.name}
    sh(["docker", "rm", "-f", box])
    sh(["docker", "pull", entry["image"]])
    up = sh(["docker", "run", "-d", "--name", box, entry["image"], "sleep", "infinity"])
    if up.returncode != 0:
        return dict(meta, error="docker run failed", stderr=up.stderr[-300:])
    try:
        repo_dir = sh(["docker", "exec", box, "bash", "-c",
                       "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
        repo = str(Path(repo_dir).parent)
        sh(["docker", "cp", str(diff), f"{box}:/tmp/patch.diff"])
        gold = BASE / "control-gold" / iid.replace("/", "_") / "gold.diff"
        sh(["docker", "cp", str(gold), f"{box}:/tmp/bug.diff"])
        bg = sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/bug.diff"])
        meta["bug_applied"] = bg.returncode == 0
        ap = sh(["docker", "exec", box, "git", "-C", repo, "apply", "--verbose", "/tmp/patch.diff"])
        meta["patch_applied"] = ap.returncode == 0 and meta["bug_applied"]
        if not meta["patch_applied"]:
            meta["apply_err"] = ap.stderr[-400:]
        if meta["patch_applied"] and entry.get("target"):
            cp = sh(["docker", "exec", box, "/opt/miniconda3/envs/testbed/bin/python",
                     "-m", "py_compile", f"{repo}/{entry['target']}"])
            meta["py_compiles"] = cp.returncode == 0
        if meta["patch_applied"] and entry.get("f2p"):
            r = sh(["docker", "exec", box, "bash", "-c",
                    f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python "
                    f"-m pytest -x -q {' '.join(entry['f2p'][:4])}"])
            meta["f2p_pass"] = r.returncode == 0
            meta["f2p_tail"] = (r.stdout + r.stderr)[-600:]
            p2p = P2P.get(iid, [])
            if meta["f2p_pass"] and p2p:
                rp = sh(["docker", "exec", box, "bash", "-c",
                         f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python "
                         f"-m pytest -q {' '.join(p2p[:20])}"])
                meta["p2p_pass"] = rp.returncode == 0
                meta["p2p_tail"] = (rp.stdout + rp.stderr)[-400:]
    finally:
        sh(["docker", "rm", "-f", box])
    return meta


def main() -> int:
    done = todo = 0
    for entry in OUT:
        for cand in entry["candidates"]:
            k = cand["k"]
            lf = LABELS / f"{entry['task'].replace('/', '_')}-cand{k}.json"
            if lf.is_file():
                done += 1
                continue
            todo += 1
            r = run_cand(entry, k)
            if r is not None:
                lf.write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
                print(entry["task"][:45], f"cand{k}",
                      "applied" if r.get("patch_applied") else "NOAPPLY",
                      "f2p" if r.get("f2p_pass") else "", flush=True)
    print(f"\n== S6 labels : {done} déjà présents, {todo} exécutés ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
