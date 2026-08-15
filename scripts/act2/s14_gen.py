#!/usr/bin/env python3
"""S14 — génération galere sur les tâches HORS pool v6 (fenêtre autonomie 8h).

Pré-enregistré dans governance/act2/budget-v1.toml (entrée 2026-08-14 nuit) :
  - 82 tâches hors v6 × 2 tirages = 164 slots, T=0.7 ;
  - auteur-modèle IDENTIQUE à S12 (MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-
    Reasoning-Distilled-bf16) — comparabilité de distribution-auteur avec v6/v7
    (leçon S11 : l'auteur est un facteur de première classe) ;
  - prompt / extrait / sanitize→apply→re-export IDENTIQUES à la classe v6
    (pilot_run.gen_patch) ; raw persistée dès le 1er appel ;
  - 1 retry instrumenté max par slot ; CAP auto-appliqué dans le script
    (S14_CAP, défaut 350) + deadline mur (S14_DEADLINE epoch, optionnel) —
    run autonome sans surveillance humaine.

 Sorties : $BASE/s14-gen/results/<slot>/{task.json,raw-aN.txt,patch.diff,meta.json}
           $BASE/s14-gen/call-log.jsonl
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
GEN = PILOT / "s14-gen"
RESULTS = GEN / "results"
LOG = GEN / os.environ.get("S14_LOGNAME", "call-log.jsonl")
import threading

MODEL = os.environ.get(
    "S14_MODEL",
    "MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-bf16")
DRAWS = int(os.environ.get("S14_DRAWS", "2"))
DRAW_START = int(os.environ.get("S14_DRAW_START", "1"))
PARALLEL = int(os.environ.get("S14_PARALLEL", "4"))
CAP = int(os.environ.get("S14_CAP", "350"))
DEADLINE = float(os.environ.get("S14_DEADLINE", "0"))
os.environ["PILOT_MODEL"] = MODEL
os.environ["PILOT_MAX_TOKENS"] = os.environ.get("PILOT_MAX_TOKENS", "16000")

_spec = importlib.util.spec_from_file_location(
    "pilot_run", ROOT / "scripts" / "act2" / "pilot_run.py")
pr = importlib.util.module_from_spec(_spec)
sys.modules["pilot_run"] = pr
_spec.loader.exec_module(pr)

_lock = threading.Lock()
_calls = 0
_stop = ""


def _buggy(task_id: str) -> Path:
    for d in (PILOT, PILOT / "extension-128"):
        p = d / f"{task_id.replace('/', '_')}.buggy.py"
        if p.is_file():
            return p
    raise FileNotFoundError(task_id)


def load_panel():
    """Tâches avec buggy.py + gold.diff + meta connue, HORS v6."""
    v6 = json.loads((PILOT / "latent-pool-v6.json").read_text())
    exclu = {r["task"] for r in v6}
    meta = {}
    for tj in (PILOT / "pilot-tasks-frozen32.json",
               PILOT / "pilot-tasks.json",
               PILOT / "extension-128" / "pilot-tasks.json",
               PILOT / "pilot-tasks-full.json"):
        if not tj.is_file():
            continue
        data = json.loads(tj.read_text())
        for t in data if isinstance(data, list) else []:
            if isinstance(t, dict) and "instance_id" in t:
                meta.setdefault(t["instance_id"], dict(t))
    panel, no_meta, seen_keys = [], [], set()
    for bp in sorted(list(PILOT.glob("*.buggy.py"))
                     + list((PILOT / "extension-128").glob("*.buggy.py"))):
        key = bp.name[: -len(".buggy.py")]
        if key in seen_keys or key in exclu:
            continue
        seen_keys.add(key)
        gold = None
        for d in (PILOT / "control-gold" / key,
                  PILOT / "extension-128" / "control-gold" / key):
            if (d / "gold.diff").is_file():
                gold = d
                break
        if gold is None:
            continue
        iid = key.replace("_", "/", 1) if "/" not in key else key
        t = meta.get(iid)
        if t is None:
            for k2, v2 in meta.items():
                if k2.replace("/", "_") == key:
                    t = v2
                    break
        if (t is None or not t.get("image") or not t.get("f2p")
                or not t.get("target") or not t.get("problem")):
            no_meta.append(key)
            continue
        t = dict(t)
        t["_buggy"] = bp.read_text()
        panel.append(t)
    print(f"panel hors v6 : {len(panel)} tâches (sans meta exploitée : "
          f"{len(no_meta)}{', ex. ' + no_meta[0] if no_meta else ''})",
          flush=True)
    return panel


def log_call(slot: str, attempt: int, prompt: str, reply: dict, rc_ok: bool):
    with _lock, LOG.open("a") as fh:
        fh.write(json.dumps({
            "ts": datetime.now(UTC).isoformat(),
            "window": "s14-gen", "slot": slot, "attempt": attempt,
            "model": MODEL, "rc_ok": rc_ok,
            "prompt_sha256": sha256(prompt.encode()).hexdigest(),
            "reply_sha256": sha256(reply.get("text", "").encode()).hexdigest(),
            "usage": reply.get("usage", {}),
        }) + "\n")


def one_draw(task: dict, k: int) -> dict:
    global _calls, _stop
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
    mode, diff, err = "no-diff", None, ""
    for attempt in (1, 2):
        with _lock:
            if _stop:
                return {"slot": slot, "patch": False, "mode": "stop:" + _stop,
                        "attempts": attempt - 1}
            if _calls >= CAP:
                _stop = "cap"
                return {"slot": slot, "patch": False, "mode": "stop:cap",
                        "attempts": attempt - 1}
            if DEADLINE and time.time() > DEADLINE:
                _stop = "deadline"
                return {"slot": slot, "patch": False, "mode": "stop:deadline",
                        "attempts": attempt - 1}
            _calls += 1
        p = prompt + (
            "\n\nYOUR PREVIOUS ATTEMPT FAILED — verbatim git-apply feedback:\n"
            f"```\n{feedback[:800]}\n```\nProduce a corrected diff." if feedback else "")
        try:
            out = pr.call_model(p)
            ok = True
        except Exception as e:  # noqa: BLE001
            out = {"text": f"ERROR: {e}", "usage": {}}
            ok = False
        (work / f"raw-a{attempt}.txt").write_text(out["text"])
        log_call(slot, attempt, p, out, ok)
        if not ok:
            feedback = "endpoint error on previous call; retry"
            continue
        mode, diff, err = "no-diff", None, ""
        edited = pr.extract_full_file(out["text"])
        if edited and original and len(edited.splitlines()) < len(original.splitlines()) * 0.5:
            edited = None
        if edited and original and edited.strip() != original.strip():
            diff, mode = pr.make_diff(original, edited, task.get("target") or ""), "whole-file"
        else:
            raw = pr.extract_diff_sanitized(out["text"])
            if raw and original:
                diff, err = pr.apply_and_export_debug(
                    original, raw + "\n", task.get("target") or "")
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
    return {"slot": slot, "patch": False, "mode": mode, "attempts": 2}


def main() -> int:
    global _calls
    RESULTS.mkdir(parents=True, exist_ok=True)
    panel = load_panel()
    jobs = [(t, k) for t in panel
            for k in range(DRAW_START, DRAW_START + DRAWS)]
    todo = [j for j in jobs
            if not ((RESULTS / f"{j[0]['instance_id'].replace('/', '_')}-d{j[1]}")
                    / "meta.json").exists()]
    _calls = sum(1 for _ in LOG.open()) if LOG.exists() else 0
    print(f"slots {len(jobs)} | à faire {len(todo)} | calls fenêtre déjà "
          f"loggés {_calls} | cap {CAP} | modèle {MODEL} | T=0.7 | "
          f"parallélisme {PARALLEL}", flush=True)
    if not todo:
        metas = [json.loads(p.read_text()) for p in RESULTS.glob("*/meta.json")]
        n_patch = sum(1 for m in metas if m.get("patch_sha256"))
        print(f"\n== S14-G : {len(metas)} slots, {n_patch} avec diff "
              f"({n_patch / max(1, len(metas)):.0%}) | calls {_calls} "
              f"| rien à faire (reprise) ==")
        return 0

    def call_t07(prompt):
        import subprocess
        key = os.environ.get("LI_GALERE_KEY") or os.environ.get("OPENCODE_GALERE_KEY")
        if not key:
            f = Path.home() / ".local/share/opencode/auth.json"
            if f.is_file():
                key = json.loads(f.read_text())["galere"]["key"]
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
            if r["mode"].startswith("stop:"):
                print(f"[{done}/{len(todo)}] STOP {r['mode']} ({_calls} calls)",
                      flush=True)
                continue
            if done % 10 == 0 or done <= 5:
                print(f"[{done}/{len(todo)}] {r['slot'][:52]:52} "
                      f"{'PATCH' if r['patch'] else '---- '} {r['mode']} "
                      f"a{r['attempts']} ({_calls} calls)", flush=True)
    metas = [json.loads(p.read_text()) for p in RESULTS.glob("*/meta.json")]
    n_patch = sum(1 for m in metas if m.get("patch_sha256"))
    print(f"\n== S14-G : {len(metas)} slots, {n_patch} avec diff "
          f"({n_patch / max(1, len(metas)):.0%}) | calls {_calls} | stop={_stop or 'fin'} ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
