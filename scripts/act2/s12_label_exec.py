#!/usr/bin/env python3
"""S12-L — labellisation docker des slots générés par s12_gen.py (node).

Protocole IDENTIQUE à pilot_node_exec.run_one / s6 (chaîne stricte) :
  image swe-smith de la tâche → apply bug gold (control-gold) → apply patch
  candidat (strict) → py_compile target → pytest F2P (-x -q, 4 premiers) →
  P2P (20 premiers, seulement si F2P vert et si la tâche en déclare).
Idempotent : run-result.json existant = skip.

Entrées sur le node :
  $BASE/s12-gen/results/<slot>/{patch.diff, meta.json, task.json}
  $BASE/control-gold/<key>/gold.diff            (tâches frozen32)
  $BASE/extension-128/control-gold/<key>/gold.diff  (tâches extension-128)
Sortie : $BASE/s12-gen/results/<slot>/run-result.json
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

BASE = Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot")
RESULTS = BASE / os.environ.get("S_LABEL_STAGE", "s12-gen") / "results"
DOCKER = os.environ.get("S12_DOCKER", "docker").split()  # ex. "sudo docker"


def sh(cmd):
    if isinstance(cmd, list) and cmd and cmd[0] == "docker":
        cmd = DOCKER + cmd[1:]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def gold_for(key: str) -> Path | None:
    for d in (BASE / "control-gold" / key,
              BASE / "extension-128" / "control-gold" / key):
        g = d / "gold.diff"
        if g.is_file():
            return g
    return None


def run_slot(slot_dir: Path) -> dict:
    mf = slot_dir / "meta.json"
    if not mf.is_file():
        tf = slot_dir / "task.json"
        iid = (json.loads(tf.read_text()).get("instance_id", "")
               if tf.is_file() else "")
        return {"task": iid, "slot": slot_dir.name, "model": None,
                "diff_mode": None, "patch_sha256": None,
                "error": "meta.json manquant (S12-G incomplet)"}
    meta = json.loads(mf.read_text())
    task = json.loads((slot_dir / "task.json").read_text())
    iid = task["instance_id"]
    key = iid.replace("/", "_")
    out = {"task": iid, "slot": slot_dir.name, "model": meta.get("model"),
           "diff_mode": meta.get("diff_mode"),
           "patch_sha256": meta.get("patch_sha256")}
    patch = slot_dir / "patch.diff"
    if not patch.is_file() or not patch.read_text().strip():
        return dict(out, error="pas de diff")
    gold = gold_for(key)
    if gold is None:
        return dict(out, error="gold.diff introuvable")
    box = f"li-s12-{key[:24]}-{slot_dir.name.rsplit('-d', 1)[-1][:3]}"
    sh(["docker", "rm", "-f", box])
    pl = sh(["docker", "pull", task["image"]])
    if pl.returncode != 0 and "Error" in pl.stderr:
        return dict(out, error="docker pull failed", stderr=pl.stderr[-300:])
    up = sh(["docker", "run", "-d", "--name", box, task["image"],
             "sleep", "infinity"])
    if up.returncode != 0:
        return dict(out, error="docker run failed", stderr=up.stderr[-300:])
    try:
        repo_dir = sh(["docker", "exec", box, "bash", "-c",
                       "find / -maxdepth 3 -name '.git' -type d | head -1"]
                      ).stdout.strip()
        if not repo_dir:
            return dict(out, error="repo .git introuvable dans l'image")
        repo = str(Path(repo_dir).parent)
        sh(["docker", "cp", str(gold), f"{box}:/tmp/bug.diff"])
        sh(["docker", "cp", str(patch), f"{box}:/tmp/patch.diff"])
        bg = sh(["docker", "exec", box, "git", "-C", repo,
                 "apply", "/tmp/bug.diff"])
        out["bug_applied"] = bg.returncode == 0
        ap = sh(["docker", "exec", box, "git", "-C", repo,
                 "apply", "--verbose", "/tmp/patch.diff"])
        out["patch_applied"] = ap.returncode == 0 and out["bug_applied"]
        if not out["patch_applied"]:
            out["apply_err"] = (bg.stderr + ap.stderr)[-400:]
        if out["patch_applied"] and task.get("target"):
            cp = sh(["docker", "exec", box,
                     "/opt/miniconda3/envs/testbed/bin/python",
                     "-m", "py_compile", f"{repo}/{task['target']}"])
            out["py_compiles"] = cp.returncode == 0
            if cp.returncode != 0:
                out["py_compile_err"] = cp.stderr[-300:]
        if out["patch_applied"] and task.get("f2p"):
            r = sh(["docker", "exec", box, "bash", "-c",
                    (f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python "
                    f"-m pytest -x -q {' '.join(map(str, task['f2p'][:4]))}")])
            out["f2p_pass"] = r.returncode == 0
            out["f2p_tail"] = (r.stdout + r.stderr)[-600:]
            p2p = task.get("p2p") or []
            if out["f2p_pass"] and p2p:
                rp = sh(["docker", "exec", box, "bash", "-c",
                         (f"cd {repo} && "
                         "/opt/miniconda3/envs/testbed/bin/python "
                         f"-m pytest -q {' '.join(map(str, p2p[:20]))}")])
                out["p2p_pass"] = rp.returncode == 0
                out["p2p_tail"] = (rp.stdout + rp.stderr)[-400:]
    finally:
        sh(["docker", "rm", "-f", box])
    return out


def main() -> int:
    slots = sorted(RESULTS.glob("*-d*"))
    done = run = 0
    stats = {"patch": 0, "f2p": 0, "f2p_and_p2p": 0}
    for sd in slots:
        rf = sd / "run-result.json"
        if rf.is_file():
            done += 1
            continue
        r = run_slot(sd)
        rf.write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
        run += 1
        stats["patch"] += bool(r.get("patch_applied"))
        stats["f2p"] += bool(r.get("f2p_pass"))
        ok_p2p = (r.get("f2p_pass")
                  and (r.get("p2p_pass") or "p2p_pass" not in r))
        stats["f2p_and_p2p"] += bool(ok_p2p)
        print(f"{sd.name[:56]:56} apply={r.get('patch_applied')} "
              f"f2p={r.get('f2p_pass')} p2p={r.get('p2p_pass')}", flush=True)
    _tag = os.environ.get("S_LABEL_STAGE", "s12-gen").upper().replace("-GEN", "")
    print(f"\n== {_tag}-L : {done} déjà mesurés, {run} exécutés | "
          f"apply {stats['patch']} f2p {stats['f2p']} "
          f"vert-complet {stats['f2p_and_p2p']} ==")
    return 0


if __name__ == "__main__":
    main()
