#!/usr/bin/env python3
"""Story 10.1 Task 2/3 — fenêtre de génération gen-families (Q1 + Q2),
budget stop-at-cap, tags campagne, no-diff abort.

Réutilise la classe prompt/extract GELÉE par référence (`pilot_run.gen_patch`
via `pr.call_model` / `pr.extract_full_file` / `pr.extract_diff_sanitized` /
`pr.apply_and_export_debug` / `pr.make_diff`) — identique à s12 (author pinned
S12/S14). Ce script ajoute SEULEMENT la discipline du window gen-families :
  - cap dur 350 appels modèle (Q1+Q2) : refuse de démarrer l'appel #351,
    loggue la tentative bloquée et stoppe proprement (S14 : le 251e appel
    in-flight fut loggé, jamais caché) ;
  - campaign tags genfam-q1 / genfam-q2, jamais mélangés avant mesure ;
  - abort par quota : si le taux no-diff après ré-extraction dépasse 60 %,
    HALT + diagnostic disclosé (règle d'abort du window, S14 précédent) ;
  - provenance par ligne {campaign, window, author, draws}, raw persisté dès
    le premier appel.

Generation locale (curl vers le serveur auteur) ; labellisation docker suit
sur le node (story 10.2). Zéro promotion automatique.

Run:  uv run python scripts/act2/genfam_gen.py --quota q1 [--cap 350] [--draws 2]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOBS = ROOT / "data" / "landing" / "act2-pilot"
SEL = ROOT / "governance" / "act2" / "genfam-q1-selection-v1.json"
STAGING = JOBS / "genfam-q1" / "staging-extract.json"

DEFAULT_CAP = 350
NODIFF_ABORT = 0.60

MODEL = os.environ.get(
    "GENFAM_MODEL",
    "MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-bf16")

_spec = importlib.util.spec_from_file_location("pilot_run", ROOT / "scripts" / "act2" / "pilot_run.py")
pr = importlib.util.module_from_spec(_spec)
sys.modules["pilot_run"] = pr
_spec.loader.exec_module(pr)


class BudgetExhausted(Exception):
    """The hard call cap was reached — the window must stop cleanly."""


def call_t07(prompt: str) -> dict:
    """Wrapper auteur-modèle GELÉ (forme s12) : modèle pinned, T=0.7,
    max_tokens 16000. pilot_run.call_model hardcode T=0.2/6000 — le window exige
    la forme s12/s14, donc on installe ce wrapper sur pr.call_model (gen_patch
    résout call_model à l'appel → le wrapper s'applique)."""
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
    p2 = subprocess.run(cmd, input=body.encode(), capture_output=True, check=False)
    if p2.returncode != 0:
        raise RuntimeError(f"curl galere rc={p2.returncode}: {p2.stderr[-300:].decode()}")
    j = json.loads(p2.stdout.decode())
    if "choices" not in j:
        raise RuntimeError(f"galere payload: {str(j)[:300]}")
    mmsg = j["choices"][0]["message"]
    return {"text": (mmsg.get("content") or "") + "\n"
            + (mmsg.get("reasoning") or mmsg.get("reasoning_content") or ""),
            "usage": j.get("usage", {})}


pr.call_model = call_t07  # installation à l'import : la classe d'appel est gelée ici


def _campaign_dir(quota: str) -> str:
    return f"genfam-{quota}"


def window_calls_used() -> int:
    """Cap commun Q1+Q2 : on compte TOUS les appels persistés des deux quotas."""
    n = 0
    for q in ("q1", "q2"):
        log = JOBS / f"genfam-{q}" / "call-log.jsonl"
        if log.is_file():
            n += sum(1 for line in log.read_text().splitlines() if line.strip())
    return n


def load_panel(quota: str, selection: dict) -> list[dict]:
    """Rows of one quota, joined with their frozen problem/patch/image from staging."""
    staging_path = JOBS / f"genfam-{quota}" / "staging-extract.json"
    if not staging_path.is_file():
        return []
    staging = {t["instance_id"]: t for t in json.loads(staging_path.read_text())["tasks"]}
    panel = []
    for row in selection[quota]:
        st = staging.get(row["instance_id"])
        if st is None:
            continue
        p = JOBS / f"genfam-{quota}" / f"{row['instance_id'].replace('/', '_')}.buggy.py"
        if not p.is_file():
            continue  # extraction not done yet; reported at summary, not faked
        panel.append({**st, "_buggy": p.read_text()})
    return panel


def call_budget(calls_made: int, cap: int) -> None:
    """Raise BEFORE starting the next call if the cap is already spent."""
    if calls_made >= cap:
        raise BudgetExhausted(f"cap {cap} atteint ({calls_made} appels) — stop au plafond")


def nodiff_abort_rate(done: int, nodiff: int) -> float | None:
    """Per-quota no-diff rate; None until enough slots to mean something."""
    if done < 5:
        return None
    return nodiff / done


def gen_panel(quota: str, panel: list[dict], draws: int, cap: int, results: Path, log: Path,
              parallel: int | None = None):
    """Exécution parallèle thread-safe : réservation d'appel SOUS LOCK avant
    chaque appel (le cap n'est jamais dépassé en concurrence), reprise
    idempotente (slot avec rec.json déjà fait = skip), arrêt no-diff/budget
    signalé par le dict `stop` puis levé proprement après shutdown."""
    if parallel is None:
        parallel = int(os.environ.get("GENFAM_PARALLEL", "4"))
    window_start_calls = window_calls_used()
    state = {"attempts": 0, "nodiff": 0, "done": 0, "rows": []}
    stop = {"reason": None}
    lock = threading.Lock()
    log.parent.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)

    def reserve() -> bool:
        with lock:
            if stop["reason"] or window_start_calls + state["attempts"] >= cap:
                stop["reason"] = stop["reason"] or "cap"
                return False
            state["attempts"] += 1
            return True

    def run_slot(task: dict, k: int) -> dict | None:
        iid = task["instance_id"]
        slot = f"{iid.replace('/', '_')}-d{k}"
        work = results / slot
        if (work / "rec.json").is_file():
            return None  # reprise idempotente
        work.mkdir(parents=True, exist_ok=True)
        (work / "task.json").write_text(json.dumps(
            {kk: v for kk, v in task.items() if kk != "_buggy"},
            indent=1, default=str))
        original = task["_buggy"]
        diff, feedback, local_calls = None, "", 0
        for attempt in (1, 2):
            if not reserve():
                break
            g = pr.gen_patch(task, feedback)
            with lock, log.open("a") as fh:  # append-only log, un appel = une ligne
                fh.write(json.dumps({
                        "ts": datetime.now(UTC).isoformat(), "window": "gen-families-v1",
                        "quota": quota, "slot": slot, "attempt": attempt, "model": MODEL,
                        "campaign": task["campaign"],
                        "prompt_sha256": g["prompt_sha256"],
                        "reply_sha256": g["reply_sha256"],
                        "raw_reply": g["raw_reply"], "usage": g["usage"],
                        "temperature": 0.7,
                        "calls_used_window": window_start_calls + state["attempts"],
                    }) + "\n")
            local_calls += 1  # raw persistée dès le PREMIER appel (leçon 08-10f S5)
            edited = pr.extract_full_file(g["raw_reply"])
            this_diff, _err, raw = None, "", None
            if (edited and edited.strip() != original.strip()
                    and len(edited.splitlines()) >= len(original.splitlines()) * 0.5):
                this_diff = pr.make_diff(original, edited, task["target"])
            if this_diff is None:
                raw = pr.extract_diff_sanitized(g["raw_reply"])
                if raw:
                    this_diff, _err = pr.apply_and_export_debug(original, raw + "\n", task["target"])
            if this_diff:
                diff = this_diff
                break
            feedback = _err if raw else \
                "no parseable diff found in your reply (must contain one ```diff block)"
        if local_calls == 0:
            rec = {"task": iid, "campaign": task["campaign"], "window": "gen-families-v1",
                   "author": MODEL, "slot": slot, "draw": k, "status": "budget-stopped",
                   "diff_sha256": None, "n_calls_used": window_start_calls + state["attempts"]}
            (work / "rec.json").write_text(json.dumps(rec, indent=1))
            return rec  # jamais compté dans done/nodiff : aucun appel n'a eu lieu
        status = "ok" if diff else "no-diff"
        rec = {"task": iid, "campaign": task["campaign"], "window": "gen-families-v1",
               "author": MODEL, "slot": slot, "draw": k, "status": status,
               "diff_sha256": sha256(diff.encode()).hexdigest() if diff else None,
               "n_calls_used": window_start_calls + state["attempts"]}
        (work / "rec.json").write_text(json.dumps(rec, indent=1))
        if diff:
            (work / "diff.patch").write_text(diff)
        with lock:
            state["rows"].append(rec)
            state["done"] += 1
            if not diff:
                state["nodiff"] += 1
            rate = nodiff_abort_rate(state["done"], state["nodiff"])
            if rate is not None and rate > NODIFF_ABORT and not stop["reason"]:
                stop["reason"] = "no-diff"
                stop["rate"] = rate
        return rec

    slots = [(t, k) for t in panel for k in range(1, draws + 1)]
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
        futs = [ex.submit(run_slot, t, k) for t, k in slots]
        for f in as_completed(futs):
            f.result()  # propage les erreurs (jamais de perte silencieuse)
    done, nodiff = state["done"], state["nodiff"]
    calls = window_start_calls + state["attempts"]
    if stop["reason"] == "cap":
        _check_budget_midway(calls, cap, results)
    if stop["reason"] == "no-diff":
        (results / "summary.json").write_text(json.dumps({
            "window": "gen-families-v1", "quota": quota, "aborted": "no-diff>60%",
            "no_diff_rate": round(stop["rate"], 3), "done": done,
            "diagnosis_needed": "sanitize/extraction regression check (règle d'abort du window)"}, indent=1))
        raise SystemExit(f"HALT {quota}: no-diff rate {stop['rate']:.0%} > 60 % après {done} slots — diagnostic requis, fenêtre stoppée (disclosé, S14)")
    (results / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in state["rows"]))
    (results / "summary.json").write_text(json.dumps({
        "quota": quota, "slots_done": done, "no_diff": nodiff, "calls_used": calls,
        "cap": cap, "window": "gen-families-v1"}, indent=1))
    return {"quota": quota, "slots_done": done, "no_diff": nodiff,
            "calls_used": calls, "cap": cap, "rows": state["rows"]}


def _check_budget_midway(calls: int, cap: int, results: Path):
    """Once the cap is spent, stop the window cleanly and write the shortfall."""
    if calls >= cap:
        results.mkdir(parents=True, exist_ok=True)
        (results / "summary.json").write_text(json.dumps({
            "window": "gen-families-v1", "aborted": "cap-reached", "calls_used": calls,
            "cap": cap,
            "note": "stop-at-cap : le reste de la fenêtre n'est pas exécuté; shortfall = amendement, jamais silencieux (discipline du window)"},
            indent=1))
        raise SystemExit(f"STOP au plafond : {calls}/{cap} appels consommés — fenêtre arrêtée proprement, shortfall disclosé")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quota", choices=("q1", "q2"), default="q1")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    ap.add_argument("--draws", type=int, default=2)
    args = ap.parse_args()
    os.environ["PILOT_CAMPAIGN_DIR"] = _campaign_dir(args.quota)
    pr.os.environ["PILOT_CAMPAIGN_DIR"] = _campaign_dir(args.quota)  # même process import
    sel = json.loads(SEL.read_text())
    key = args.quota
    panel = load_panel(key, sel)
    if not panel:
        print(f"Aucune tâche prête pour {key} (extraction non faite ?) — rien à générer, disclose.")
        return 1
    results = JOBS / f"genfam-{key}" / "gen-results"
    log = JOBS / f"genfam-{key}" / "call-log.jsonl"
    out = gen_panel(key, panel, args.draws, args.cap, results, log)
    print(f"{key}: {out['slots_done']} slots, {out['no_diff']} no-diff, "
          f"{out['calls_used']}/{out['cap']} appels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
