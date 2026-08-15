#!/usr/bin/env python3
"""S12 — génération galere pour pousser le pool latent vers 200+ patchs labelisés.

Pré-enregistré dans governance/act2/budget-v1.toml (entrée 2026-08-14) :
  - 156 slots = 78 tâches v6 × 2 tirages, T=0.7 (diversité ; même classe que les
    candidats boltzmann-e1 déjà dans v6) ;
  - auteur-modèle déclaré : MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-
    Distilled-bf16 — substitut in-family de Qwen3.6-35B-A3B-FP8 retiré du roster
    (mesuré avant ce run) ; max_tokens 16000 (ladder finding #4) ;
  - prompt / extrait / sanitize→apply→re-export IDENTIQUES à la classe v6
    (pilot_run.gen_patch) ; raw persistée dès le 1er appel (leçon 08-10f S5) ;
  - retries instrumentés (feedback git-apply) max 1 par slot (leçon pilote #4).

Tourne sur le Mac (curl galere). La labellisation docker suit sur le node
(s12_label_exec.py). Zéro promotion automatique : l'entrée au pool et la gate v2
restent à la main de l'owner.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
GEN = PILOT / "s12-gen"
RESULTS = GEN / "results"
LOG = GEN / "call-log.jsonl"

MODEL = os.environ.get(
    "S12_MODEL",
    "MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-bf16")
DRAWS = int(os.environ.get("S12_DRAWS", "2"))
PARALLEL = int(os.environ.get("S12_PARALLEL", "4"))
os.environ["PILOT_MODEL"] = MODEL
os.environ["PILOT_MAX_TOKENS"] = os.environ.get("PILOT_MAX_TOKENS", "16000")

_spec = importlib.util.spec_from_file_location(
    "pilot_run", ROOT / "scripts" / "act2" / "pilot_run.py")
pr = importlib.util.module_from_spec(_spec)
sys.modules["pilot_run"] = pr
_spec.loader.exec_module(pr)


def _buggy(task_id: str) -> Path:
    for d in (PILOT, PILOT / "extension-128"):
        p = d / f"{task_id.replace('/', '_')}.buggy.py"
        if p.is_file():
            return p
    raise FileNotFoundError(task_id)


def load_panel():
    """78 tâches v6, meta depuis frozen32 / extension-128 / full."""
    v6 = json.loads((PILOT / "latent-pool-v6.json").read_text())
    vt = sorted({r["task"] for r in v6})
    f32 = {t["instance_id"]: t
           for t in json.loads((PILOT / "pilot-tasks-frozen32.json").read_text())}
    ext = {t["instance_id"]: t
           for t in json.loads((PILOT / "pilot-tasks.json").read_text())}
    full = json.loads((PILOT / "pilot-tasks-full.json").read_text())
    meta = {}
    for t in vt:
        if t in f32:
            meta[t] = dict(f32[t])
        elif t in ext:
            meta[t] = dict(ext[t])
        elif t in full:
            meta[t] = dict(full[t])
        else:
            raise KeyError(t)
        p = _buggy(t)
        meta[t]["_buggy"] = p.read_text()
    return [meta[t] for t in vt]


def log_call(slot: str, attempt: int, prompt: str, reply: dict, rc_ok: bool):
    with LOG.open("a") as fh:
        fh.write(json.dumps({
            "ts": datetime.now(UTC).isoformat(),
            "window": "s12-gen", "slot": slot, "attempt": attempt,
            "model": MODEL, "rc_ok": rc_ok,
            "prompt_sha256": sha256(prompt.encode()).hexdigest(),
            "reply_sha256": sha256(reply.get("text", "").encode()).hexdigest(),
            "usage": reply.get("usage", {}),
        }) + "\n")


def one_draw(task: dict, k: int) -> dict:
    """Un slot : 1 appel (+1 retry instrumenté si pas de diff). Retour sommaire."""
    iid = task["instance_id"]
    slot = f"{iid.replace('/', '_')}-d{k}"
    work = RESULTS / slot
    work.mkdir(parents=True, exist_ok=True)
    (work / "task.json").write_text(
        json.dumps({k2: v for k2, v in task.items() if k2 != "_buggy"}, indent=1))
    prompt = (
        "Fix failing tests. Output ONLY a unified diff inside ```diff fences "
        "(paths a/<file> b/<file>). The diff must apply with `git apply`. No prose.\n"
        f"File to patch: {task.get('target', 'the affected file')}\n\n"
        f"TASK: {task['problem'][:1200]}\n\n"
        f"FAILING TESTS: {'; '.join(map(str, task['f2p'][:6]))}\n\n"
        f"CURRENT CONTENT (verbatim):\n```python\n{task['_buggy']}\n```"
    )
    original = task["_buggy"]
    feedback = ""
    for attempt in (1, 2):
        p = prompt + (
            "\n\nYOUR PREVIOUS ATTEMPT FAILED — verbatim git-apply feedback:\n"
            f"```\n{feedback[:800]}\n```\nProduce a corrected diff." if feedback else "")
        try:
            out = pr.call_model(p)
            ok = True
        except Exception as e:  # noqa: BLE001
            out = {"text": f"ERROR: {e}", "usage": {}}
            ok = False
        raw_file = work / f"raw-a{attempt}.txt"
        raw_file.write_text(out["text"])  # raw persistée AVANT tout traitement
        log_call(slot, attempt, p, out, ok)
        if not ok:
            feedback = "endpoint error on previous call; retry"
            continue
        mode, diff, err = "no-diff", None, ""
        edited = pr.extract_full_file(out["text"])
        if edited and original and len(edited.splitlines()) < len(original.splitlines()) * 0.5:
            edited = None  # garde-fou whole-file résumé
        if edited and original and edited.strip() != original.strip():
            diff, mode = pr.make_diff(original, edited, task["target"]), "whole-file"
        else:
            raw = pr.extract_diff_sanitized(out["text"])
            if raw and original:
                diff, err = pr.apply_and_export_debug(original, raw + "\n", task["target"])
                mode = "model-applied-reexport" if diff else "unappliable"
        if diff:
            (work / "patch.diff").write_text(diff)
            meta = {"task": iid, "slot": slot, "draw": k, "model": MODEL,
                    "temperature": 0.7, "attempt_used": attempt, "diff_mode": mode,
                    "patch_sha256": sha256(diff.encode()).hexdigest(),
                    "prompt_sha256": sha256(p.encode()).hexdigest(),
                    "reply_sha256": sha256(out["text"].encode()).hexdigest(),
                    "run_at": datetime.now(UTC).isoformat()}
            (work / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True))
            return {"slot": slot, "patch": True, "mode": mode, "attempts": attempt}
        feedback = err or "no parseable diff found in your reply (must contain one ```diff block)"
    meta = {"task": iid, "slot": slot, "draw": k, "model": MODEL,
            "temperature": 0.7, "attempt_used": 2, "diff_mode": "no-diff",
            "patch_sha256": None,
            "run_at": datetime.now(UTC).isoformat()}
    (work / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True))
    return {"slot": slot, "patch": False, "mode": "no-diff", "attempts": 2}


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    panel = load_panel()
    jobs = [(t, k) for t in panel for k in range(1, DRAWS + 1)]
    # reprise idempotente : slot déjà complété = skip
    todo = [j for j in jobs
            if not ((RESULTS / f"{j[0]['instance_id'].replace('/', '_')}-d{j[1]}")
                    / "meta.json").exists()]
    print(f"panel {len(panel)} tâches | slots {len(jobs)} | à faire {len(todo)} "
          f"| modèle {MODEL} | T=0.7 | parallélisme {PARALLEL}", flush=True)
    if not todo:
        return 0
    # T=0.7 : on monkey-patche le body de call_model via wrapper

    def call_t07(prompt):
        import subprocess
        key = os.environ.get("LI_GALERE_KEY") or os.environ.get("OPENCODE_GALERE_KEY")
        body = json.dumps({
            "model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": int(os.environ.get("PILOT_MAX_TOKENS", "16000")),
        })
        cmd = ["curl", "-sS", "--max-time", "580", "-X", "POST", pr.GALERE,
               "-H", "Content-Type: application/json",
               "-H", "User-Agent: opencode/1.0", "--data-binary", "@-"]
        if key:
            cmd += ["-H", f"Authorization: Bearer {key}"]
        p = subprocess.run(cmd, input=body.encode(), capture_output=True, check=False)
        if p.returncode != 0:
            raise RuntimeError(f"curl galere rc={p.returncode}: {p.stderr[-300:].decode()}")
        j = json.loads(p.stdout.decode())
        if "choices" not in j:
            raise RuntimeError(f"galere payload: {str(j)[:300]}")
        mmsg = j["choices"][0]["message"]
        return {"text": (mmsg.get("content") or "") + "\n"
                + (mmsg.get("reasoning") or mmsg.get("reasoning_content") or ""),
                "usage": j.get("usage", {})}

    pr.call_model = call_t07
    done = 0
    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        futs = {ex.submit(one_draw, t, k): (t["instance_id"], k) for t, k in todo}
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            print(f"[{done}/{len(todo)}] {r['slot'][:52]:52} "
                  f"{'PATCH' if r['patch'] else '---- '} {r['mode']} a{r['attempts']}",
                  flush=True)
    metas = [json.loads(p.read_text()) for p in RESULTS.glob("*/meta.json")]
    n_patch = sum(1 for mmet in metas if mmet.get("patch_sha256"))
    print(f"\n== S12-G : {len(metas)} slots, {n_patch} avec diff "
          f"({n_patch / max(1, len(metas)):.0%}) ==")
    calls = sum(1 for _ in LOG.open()) if LOG.exists() else 0
    print(f"calls loggés fenêtre S12 : {calls} (cap pré-enregistré 250)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
