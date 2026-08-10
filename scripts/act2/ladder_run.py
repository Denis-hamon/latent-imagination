#!/usr/bin/env python3
"""Ladder-v1 — baselines absolues 2 modèles sur le panel gelé frozen32.

Pré-enregistrement : governance/act2/ladder-prereg-v1.md (scellé OTS avant spend).
Un appel par (modèle × tâche), aucun retry, ITT (pas de candidat = échec).
Cap dur : 64 calls au total (call-log compté), arrêt sec avec publication partielle.

Sortie : data/landing/act2-pilot/ladder-v1/results/{task}-m-{slug}/patch.diff + meta.json
+ reply.raw.txt  — compatible pilot_node_exec.py (PILOT_ARMS=m-deepseek,m-glm).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "act2"))
import pilot_run as pr
from rct_wm_fork import base_prompt, call_model_robust


def extract_and_apply(task: dict, src: str, reply: str):
    """Variante ladder (amendement-1 ladder-prereg, avant résultats) :
    parmi TOUS les blocs ```python, retenir le PLUS LONG (les modèles à
    raisonnement étendu émettent des dizaines de snippets ; le fichier corrigé
    est le bloc le plus substantiel), garde 0.5 puis chaîne canonique."""
    import re
    blocks = re.findall(r"```python\n(.*?)```", reply, re.DOTALL)
    cand = max(blocks, key=len) if blocks else None
    if cand and src and cand.strip() != src.strip() and \
            len(cand.splitlines()) >= len(src.splitlines()) * 0.5:
        return pr.make_diff(src, cand, task["target"]), "regenerated", ""
    raw = pr.extract_diff_sanitized(reply)
    if raw and src:
        d, err = pr.apply_and_export_debug(src, raw + "\n", task["target"])
        return d, ("model-applied-reexport" if d else "unappliable"), ("" if d else err)
    return None, "no-diff", ""

PILOT = ROOT / "data" / "landing" / "act2-pilot"
LAD = PILOT / "ladder-v1"
JOBS = LAD / "results"
LOG = LAD / "call-log.jsonl"

MODELS = {"m-deepseek": "DeepSeek-V4-Flash-max", "m-glm": "GLM-5.2-NVFP4"}
CAP_TOTAL = 64


def calls_used() -> int:
    return sum(1 for _ in LOG.open()) if LOG.is_file() else 0


def log_call(**kw):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"ts": datetime.now(UTC).isoformat(), **kw}) + "\n")


def main() -> int:
    tasks = json.loads((PILOT / "pilot-tasks-frozen32.json").read_text())
    JOBS.mkdir(parents=True, exist_ok=True)
    (LAD / "pilot-tasks.json").write_text(json.dumps(tasks, indent=1))
    for slug, model in MODELS.items():
        for task in tasks:
            iid = task["instance_id"]
            key = iid.replace("/", "_")
            outdir = JOBS / f"{key}-{slug}"
            outdir.mkdir(parents=True, exist_ok=True)
            if (outdir / "meta.json").is_file():
                continue  # reprise idempotente
            if calls_used() >= CAP_TOTAL:
                print(f"cap {CAP_TOTAL} atteint — publication partielle (voir ladder-prereg)")
                return 0
            src_p = PILOT / f"{key}.buggy.py"
            src = src_p.read_text() if src_p.is_file() else ""
            prompt = base_prompt(task, src)
            pr.MODEL = model                     # payload "model" vient du module-global
            # amendement-2 finding : modèles à raisonnement long → le livrable meurt
            # sous le plafond de completion ; le replay exige ≥16k (PILOT_MAX_TOKENS)
            g = call_model_robust(prompt)
            log_call(task=iid, arm=slug, model=model,
                     prompt_sha256=sha256(prompt.encode()).hexdigest(),
                     reply_sha256=sha256(g["text"].encode()).hexdigest(), usage=g["usage"])
            (outdir / "reply.raw.txt").write_text(g["text"])
            diff, mode, err = extract_and_apply(task, src, g["text"])
            meta = {"task": iid, "arm": slug, "model": model,
                    "run_at": datetime.now(UTC).isoformat(),
                    "attempts": [{"n": 1, "mode": mode}],
                    "patch_sha256": sha256((diff or "").encode()).hexdigest() if diff else None,
                    "apply_err": err[-300:] if err else ""}
            if diff:
                (outdir / "patch.diff").write_text(diff)
            (outdir / "meta.json").write_text(json.dumps(meta, indent=1))
            print(f"{key[:48]:48s} {slug:10s} {meta['patch_sha256'] or 'NO-CANDIDAT'}",
                  flush=True)
    print(f"\ncalls: {calls_used()} / cap {CAP_TOTAL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
