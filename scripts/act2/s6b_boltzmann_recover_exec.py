#!/usr/bin/env python3
"""S6b — récupération des diffs boltzmann corrompus par la procédure canonique.

S6 a appliqué les 128 candidats en `git apply` STRICT (copie de run_one) : 92
NOAPPLY = diffs jamais passés par le pipeline historique du pilot (sanitize →
git apply --recount contre l'état buggy → ré-export `git diff` propre). Le pilot
faisait ça EN AMONT du node ; les candidats E1 sont bruts de génération T=0.7.

Pour chaque NOAPPLY (bug gold applicable) :
  container image → apply bug → extraction des fichiers cibles à l'état BUGGY →
  repo git temporaire local (baseline commit) → sanitize_diff → apply --recount →
  git diff = patch PROPRE → container neuf : bug + patch propre → py_compile →
  pytest F2P → P2P si vert. Label réécrit avec recovered=true. Idempotent.

Leçon devenu pipeline : les raw diffs LLM ne sont JAMAIS appliqués strict.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

BASE = Path("/home/ubuntu/latent-imagination/data/landing/act2-pilot")
OUT = json.loads((BASE / "boltzmann-out.json").read_text())
LABELS = BASE / "boltzmann-e1" / "labels"
BY_TASK = {e["task"]: e for e in OUT}
P2P = {t["instance_id"]: t.get("p2p", [])
       for t in json.loads((BASE / "pilot-tasks-frozen32.json").read_text())}


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def sanitize_diff(diff: str) -> str:
    """Identique à pilot_run.sanitize_diff (canonique)."""
    keep = []
    prefixes = ("--- ", "+++ ", "@@ ", "index ", "diff --git ", "new file",
                "old mode", "new mode")
    for ln in diff.splitlines():
        s = ln.rstrip()
        if s.startswith(("+diff>", "</diff>", "</patch>", "</change>")):
            continue
        if s.startswith(prefixes) or s.startswith(("-", "+", " ", "\\ ")):
            keep.append(s)
        elif not keep:
            continue
        else:
            break
    out = "\n".join(keep)
    return out + "\n" if out else ""


def clean_patch(diff_raw: str, buggy_files: dict[str, str]) -> str | None:
    """Repo temporaire à l'état buggy → apply --recount → git diff propre."""
    patch = sanitize_diff(diff_raw)
    if not patch.strip() or "@@ " not in patch:
        return None
    with tempfile.TemporaryDirectory() as td:
        for rel, content in buggy_files.items():
            f = Path(td) / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content)
        sh(["git", "-C", td, "init", "-q"])
        sh(["git", "-C", td, "add", "-f", "."])
        sh(["git", "-C", td, "-c", "user.email=s6b@li", "-c", "user.name=s6b",
            "commit", "-qm", "buggy"])
        r = sh(["git", "-C", td, "apply", "--recount", "-"], input=patch)
        if r.returncode != 0:
            return None
        out = sh(["git", "-C", td, "diff", "--no-color", "--no-ext-diff", "HEAD"])
        return out.stdout if out.stdout.strip() else None


def exec_full(entry, k, patch_text, meta0):
    """Chaîne complète : bug + patch propre + py_compile + F2P (+P2P)."""
    iid = entry["task"]
    box = f"li-s6b-{iid.split('.')[0].replace('/', '_')[:16]}-{k}"
    meta = dict(meta0)
    sh(["docker", "rm", "-f", box])
    up = sh(["docker", "run", "-d", "--name", box, entry["image"], "sleep", "infinity"])
    if up.returncode != 0:
        return dict(meta, error="docker run failed 2e passe")
    try:
        repo_dir = sh(["docker", "exec", box, "bash", "-c",
                       "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
        repo = str(Path(repo_dir).parent)
        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False) as tf:
            tf.write(patch_text)
            tmp = tf.name
        sh(["docker", "cp", tmp, f"{box}:/tmp/patch2.diff"])
        gold = BASE / "control-gold" / iid.replace("/", "_") / "gold.diff"
        sh(["docker", "cp", str(gold), f"{box}:/tmp/bug.diff"])
        bg = sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/bug.diff"])
        meta["bug_applied"] = bg.returncode == 0
        ap = sh(["docker", "exec", box, "git", "-C", repo, "apply", "--verbose", "/tmp/patch2.diff"])
        meta["patch_applied"] = ap.returncode == 0 and meta["bug_applied"]
        if not meta["patch_applied"]:
            meta["apply_err_2"] = ap.stderr[-300:]
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
        Path(tmp).unlink(missing_ok=True)
    finally:
        sh(["docker", "rm", "-f", box])
    return meta


def main() -> int:
    todo = []
    for lf in sorted(LABELS.glob("*.json")):
        j = json.loads(lf.read_text())
        if j.get("error") == "diff absente/vide":
            continue
        if not j.get("patch_applied") and j.get("bug_applied") and not j.get("recovered"):
            todo.append((lf, j))
    print(f"S6b : {len(todo)} candidats NOAPPLY à récupérer", flush=True)
    ok = f2p = 0
    for lf, j in todo:
        iid, k = j["task"], j["cand"]
        entry = BY_TASK[iid]
        diff_raw = (BASE / "boltzmann-e1" / lf.name.replace(".json", ".diff")).read_text()
        # fichiers cibles du diff, lus à l'état buggy depuis UN container
        paths = re.findall(r"^\+\+\+ b/(.+)$", sanitize_diff(diff_raw), re.M)
        paths = [p for p in dict.fromkeys(paths) if p != "/dev/null"]
        box = f"li-s6b-src-{iid.split('.')[0].replace('/', '_')[:16]}-{k}"
        sh(["docker", "rm", "-f", box])
        up = sh(["docker", "run", "-d", "--name", box, entry["image"], "sleep", "infinity"])
        if up.returncode != 0:
            continue
        try:
            repo_dir = sh(["docker", "exec", box, "bash", "-c",
                           "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
            repo = str(Path(repo_dir).parent)
            gold = BASE / "control-gold" / iid.replace("/", "_") / "gold.diff"
            sh(["docker", "cp", str(gold), f"{box}:/tmp/bug.diff"])
            sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/bug.diff"])
            buggy = {}
            for p in paths:
                rd = sh(["docker", "exec", box, "cat", f"{repo}/{p}"])
                if rd.returncode == 0:
                    buggy[p] = rd.stdout
        finally:
            sh(["docker", "rm", "-f", box])
        if paths and len(buggy) != len(paths):
            j["recover_note"] = f"chemins illisibles {len(buggy)}/{len(paths)}"
            lf.write_text(json.dumps(j, indent=1, sort_keys=True) + "\n")
            continue
        clean = clean_patch(diff_raw, buggy)
        if not clean:
            j["recover_note"] = "sanitize+recount insuffisant"
            lf.write_text(json.dumps(j, indent=1, sort_keys=True) + "\n")
            continue
        meta = exec_full(entry, k, clean,
                         {**j, "recovered": True, "clean_diff": clean})
        lf.write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")
        ok += bool(meta.get("patch_applied"))
        f2p += bool(meta.get("f2p_pass"))
        print(f"  {iid[:42]} cand{k} -> applied={meta.get('patch_applied')} "
              f"f2p={bool(meta.get('f2p_pass'))}", flush=True)
    print(f"\n== S6b : {ok} récupérés applicables, {f2p} F2P verts sur {len(todo)} ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
