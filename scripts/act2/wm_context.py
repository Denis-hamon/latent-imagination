#!/usr/bin/env python3
"""wm_context — constructeur du bloc « contexte-conséquence » pour l'arm B du RCT.

Entrées : une tâche (problem + f2p names) et un brouillon de diff (draft).
Sortie : le bloc texte injecté au 2ᵉ appel, bâti UNIQUEMENT depuis le pool
(113 patchs labellisés) avec **exclusion stricte de la tâche cible** —
production = tâche jamais vue ; toute inclusion serait une fuite.

Trois composantes, chacune adossée à une mesure du repo :
  1. score attracteur F1 (d_fail_min − d_pass_min sur composites état+diff) — G1
  2. near-miss : 3 situations proches du DRAFT, tâches distinctes, avec outcome
  3. taux d'outcome des voisins de l'ÉTAT (issue→issue) — le prior de la tâche

Usage standalone (debug) :  python wm_context.py <task_idx>   (sur pilot-tasks-frozen32)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"

_model = _tok = None


def _ensure_model():
    global _model, _tok
    if _model is None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from transformers import AutoModel, AutoTokenizer
        _tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
        _model = AutoModel.from_pretrained("microsoft/unixcoder-base").eval()


def embed(texts: list[str]):
    import numpy as np
    import torch
    _ensure_model()
    out = []
    for i in range(0, len(texts), 16):
        tb = _tok(texts[i:i + 16], padding=True, truncation=True, max_length=512,
                  return_tensors="pt")
        with torch.no_grad():
            out.append(_model(**tb).last_hidden_state[:, 0].numpy())
    v = np.concatenate(out)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


_POOL = None


def pool(emb_dir: Path | None = None):
    """Charge pool + composites, une fois. Retourne (rows, E_s, cd, y, tasks)."""
    global _POOL
    if _POOL is None:
        import numpy as np
        base = emb_dir or PILOT
        rows = json.loads((base / "latent-pool.json").read_text())
        d = np.load(base / "latent-pool.npz")
        E_s = d["E_state"] / (np.linalg.norm(d["E_state"], axis=1, keepdims=True) + 1e-9)
        E_d = d["E_diff"] / (np.linalg.norm(d["E_diff"], axis=1, keepdims=True) + 1e-9)
        cd = E_s + E_d
        cd /= np.linalg.norm(cd, axis=1, keepdims=True) + 1e-9
        y = np.array([int(r["y"]) for r in rows])
        tasks = np.array([r["task"] for r in rows])
        _POOL = (rows, E_s, cd, y, tasks)
    return _POOL


STATE_TMPL = "{problem}\n{f2p}"


def build_context(task_problem: str, task_f2p: list[str], draft_diff: str,
                  exclude_task: str, k_near: int = 3) -> str:
    """Le bloc texte. `exclude_task` est EXCLU du retrieval (anti-fuite RCT)."""
    import numpy as np
    rows, E_s, cd, y, tasks = pool()

    state_text = STATE_TMPL.format(problem=task_problem[:1200],
                                   f2p="; ".join(map(str, task_f2p[:6])))
    e_state, e_draft = embed([state_text, draft_diff or "no diff yet"])
    c_draft = e_state + e_draft
    c_draft /= np.linalg.norm(c_draft) + 1e-9

    keep = tasks != exclude_task            # ANTI-FUITE : la tâche cible n'existe pas
    cd_k, y_k, rows_k = cd[keep], y[keep], [r for r, m in zip(rows, keep) if m]
    E_s_k = E_s[keep]

    # 1) attracteur F1 vs pool des autres tâches
    sims_draft = cd_k @ c_draft
    d_fail = 1.0 - sims_draft[y_k == 0]
    d_pass = 1.0 - sims_draft[y_k == 1]
    f1 = float(d_fail.min() - d_pass.min())       # >0 : plus proche des succès
    zone = ("HIGH RISK — closer to past failures" if f1 < 0
            else "low risk — closer to past successes") if len(d_fail) and len(d_pass) else "n/a"

    # 2) near-miss sur le draft, dédup par tâche
    order = np.argsort(-sims_draft)
    near, seen = [], set()
    for j in order:
        r = rows_k[int(j)]
        if r["task"] in seen:
            continue
        seen.add(r["task"])
        near.append({"task": f"{r['task'].split('.')[0]}.{r['task'].split('.')[1][:6]}",
                     "y": int(y_k[int(j)]), "sim": float(sims_draft[int(j)])})
        if len(near) >= k_near:
            break

    # 3) prior de l'état : outcomes des tâches aux issues similaires
    sims_state = E_s_k @ e_state
    top_s = np.argsort(-sims_state)[:5]
    prior = float(y_k[top_s].mean())

    lines = [
        "CONSEQUENCE-CONTEXT (instrument, measured on 113 past patches, other tasks only):",
        (f"- draft risk: {zone} (attractor score {f1:+.3f}, >0 is good; "
        f"calibrated F2P-fail landscape, AUC 0.709 goal-free)"),
        "- nearest past patches to your draft (deduped by task, outcome 1=tests passed):",
        *[f"    sim {n['sim']:.3f} | outcome {n['y']} | {n['task']}" for n in near],
        f"- tasks with similar problem statements passed F2P at rate {prior:.2f} (5 nearest)",
        ("If zone is HIGH RISK or neighbors mostly show outcome 0: shrink the diff, "
        "touch only the failing function, keep names/signatures intact."),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    tasks = json.loads((PILOT / "pilot-tasks-frozen32.json").read_text())
    t = tasks[int(sys.argv[1]) if len(sys.argv) > 1 else 0]
    fake_draft = f"diff --git a/{t['target']} b/{t['target']}\n@@ -1,1 +1,1 @@\n-x\n+y\n"
    print(build_context(t["problem"], t["f2p"], fake_draft, exclude_task=t["instance_id"]))
