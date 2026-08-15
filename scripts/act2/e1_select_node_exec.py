#!/usr/bin/env python3
"""E1 node-side : encodage + énergie + eval F2P, contre-random per-task.

Pour chaque tâche figée :
  - encodage des 4 candidats (uniXCoder, frozen)
  - énergie e_k = 1 − cos(state+diff_k, state+gold)
  - choix A = argmin e  (théorie)
  - choix B = uniform   (contrôle, seed 6769)
  - applique gold+best-with-mutation, pytest F2P (docker)
Sortie : data/landing/act2-pilot/e1-f2p.json  (sans fil bruité, les faits).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path("/home/ubuntu/latent-imagination")
PILOT = ROOT / "data" / "landing" / "act2-pilot"


def sh(cmd, timeout=900):
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)


def main() -> int:
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer

    boltz = json.loads((PILOT / "boltzmann-out.json").read_text())
    tasks = {t["instance_id"]: t for t in json.loads((PILOT / "pilot-tasks-frozen32.json").read_text())}
    pool = json.loads((PILOT / "latent-pool.json").read_text())
    # embeddings état+but du pool réel (déjà cpu-sauvés) — reload npz pour réutiliser les vecteurs
    d = np.load(PILOT / "latent-pool.npz")
    E_s_by_key = {}
    E_g_by_task = {}
    for i, r in enumerate(pool):
        E_s_by_key[r["task"]] = d["E_state"][i]
        E_g_by_task[r["task"]] = d["E_goal"][i]
    # les 18 tâches gelées qui n'ont PAS de résultat (elle n'ont pas de repère
    # latent) : leur vecteur (s, g) est encodé à la volée en utilisant les
    # mêmes données visibles — pipeline strictement identique sans gruger.
    meta_tasks = {t["instance_id"]: t for t in json.loads((PILOT / "pilot-tasks-frozen32.json").read_text())}
    golds = {}
    for iid in meta_tasks:
        g = PILOT / "control-gold" / iid.replace("/", "_") / "gold.diff"
        if g.is_file():
            golds[iid] = g.read_text()

    wait_encode = []  # (task, state_text, gold_text) pour ceux qui ne sont pas dans le pool
    for r in boltz:
        if r["task"] not in E_s_by_key:
            t = meta_tasks[r["task"]]
            state_text = t["problem"][:1200] + "\n" + "; ".join(map(str, t["f2p"][:6]))
            gold_text = golds.get(r["task"], "")
            wait_encode.append((r["task"], state_text, gold_text))

    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    model = AutoModel.from_pretrained("microsoft/unixcoder-base").to("cuda").eval()

    # encode à la volée pour les 18 tâches hors pool
    if wait_encode:
        def _enc_all(texts):
            norms = []
            for i in range(0, len(texts), 16):
                tb = tok(texts[i:i+16], padding=True, truncation=True, max_length=512,
                         return_tensors="pt").to("cuda")
                with torch.no_grad():
                    h = model(**tb).last_hidden_state[:, 0].cpu().numpy()
                norms.append(h / (np.linalg.norm(h, axis=1, keepdims=True) + 1e-9))
            return np.concatenate(norms)
        s_new = _enc_all([s for _, s, _ in wait_encode])
        g_new = _enc_all([g for _, _, g in wait_encode])
        for (tid, _, _), s_vec, g_vec in zip(wait_encode, s_new, g_new):
            E_s_by_key[tid] = s_vec
            E_g_by_task[tid] = g_vec

    def enc(txt):
        tb = tok([txt], padding=True, truncation=True, max_length=512, return_tensors="pt").to("cuda")
        with torch.no_grad():
            h = model(**tb).last_hidden_state[0, 0]
        v = h.cpu().numpy()
        return v / (np.linalg.norm(v) + 1e-9)

    rng = np.random.default_rng(6769)
    out = []
    for i, row in enumerate(boltz):
        t = tasks[row["task"]]
        Es = E_s_by_key[row["task"]]
        Eg = E_g_by_task[row["task"]]
        cands = []
        for c in row["candidates"]:
            # Les chemins enregistrés sont ceux de la machine de génération (Mac) ;
            # on recalcule le chemin local depuis le dossier boltzmann-e1/ du node.
            cand_name = Path(c["diff_file"]).name
            txt = (PILOT / "boltzmann-e1" / cand_name).read_text()
            Ed = enc(txt)
            comb_s_d = Es + Ed
            comb_s_d /= (np.linalg.norm(comb_s_d) + 1e-9)
            comb_s_g = Es + Eg
            comb_s_g /= (np.linalg.norm(comb_s_g) + 1e-9)
            energy = float(1 - (comb_s_d * comb_s_g).sum())
            cands.append({"k": c["k"], "energy": energy, "diff": txt})
        # ky choice
        best = min(cands, key=lambda x: x["energy"])
        rand = cands[int(rng.integers(len(cands)))]
        out.append({"task": row["task"], "image": t["image"], "target": t["target"],
                    "f2p": t["f2p"], "cands_energy": [c["energy"] for c in cands],
                    "pick_theory": best, "pick_random": rand["k"]})
        print(f"[{i + 1}/{len(boltz)}] {row['task'][:44]:44} energies {['{:.3f}'.format(c['energy']) for c in cands]} pick=thk k={best['k']}", flush=True)

    # F2P eval on the two picks
    def _eval(task_row, diff_text):
        img = task_row["image"]
        key = task_row["task"].replace("/", "_")[:30]
        box = f"li-e1-{abs(hash(key)) % 9999}"
        sh(["docker", "rm", "-f", box])
        up = sh(["docker", "run", "-d", "--name", box, img, "sleep", "900"])
        if up.returncode != 0:
            return {"f2p_pass": None, "err": "docker-run failed"}
        try:
            repo_dir = sh(["docker", "exec", box, "bash", "-c",
                           "find / -maxdepth 3 -name '.git' -type d | head -1"]).stdout.strip()
            repo = str(Path(repo_dir).parent) if repo_dir else "/testbed"
            (PILOT / "e1-tmp.diff").write_text(diff_text)
            sh(["docker", "cp", str(PILOT / "e1-tmp.diff"), f"{box}:/tmp/p.diff"])
            gold = PILOT / "control-gold" / key / "gold.diff"
            sh(["docker", "cp", str(gold), f"{box}:/tmp/bug.diff"]) if gold.is_file() else None
            sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/bug.diff"])
            ap = sh(["docker", "exec", box, "git", "-C", repo, "apply", "/tmp/p.diff"])
            if ap.returncode != 0:
                return {"f2p_pass": False, "note": "patch-inappliquable"}
            t = " ".join(task_row["f2p"][:4])
            r = sh(["docker", "exec", box, "bash", "-c",
                    f"cd {repo} && /opt/miniconda3/envs/testbed/bin/python -m pytest -x -q {t}"])
            return {"f2p_pass": r.returncode == 0, "tail": (r.stdout + r.stderr)[-300:]}
        finally:
            sh(["docker", "rm", "-f", box])

    eval_out = []
    for j, o in enumerate(out):
        for label in ("theory", "random"):
            if label == "theory":
                diff_txt = o["pick_theory"]["diff"]
            else:
                k = o["pick_random"]
                cd = next(c for c in boltz[j]["candidates"] if c["k"] == k)
                diff_txt = (PILOT / "boltzmann-e1" / Path(cd["diff_file"]).name).read_text()
            r = _eval(o, diff_txt)
            eval_out.append({"task": o["task"], "arm": label, **r})
            print(f"  eval [{j+1}/{len(out)}] {label} {o['task'][:40]} → {r['f2p_pass']}", flush=True)
    (PILOT / "e1-f2p.json").write_text(json.dumps(eval_out, indent=1))
    nt = [r for r in eval_out if r["arm"] == "theory"]
    nr = [r for r in eval_out if r["arm"] == "random"]
    print(f"\nE1: theory F2P-pass {sum(1 for r in nt if r['f2p_pass'])}/{len(nt)} | "
          f"random {sum(1 for r in nr if r['f2p_pass'])}/{len(nr)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
