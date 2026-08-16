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
INFRA_STOP = 8  # erreurs endpoint CONSÉCUTIVES (tous workers) ⇒ pause fenêtre :
# on ne brûle pas l'enveloppe sur un endpoint mort — le watchdog reprend
# (rétro épic 10 item 1, incident 2026-08-16 : 124 appels perdus en 500)

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


def apply_fuzz_reexport(original: str, patch_text: str, rel: str) -> tuple[str | None, str]:
    """Lane de récupération (lignage sanitize 3516b5e) : git apply strict échoue
    souvent sur la géométrie de hunk (off-by-one EOF des modèles T=0.7) alors que
    le diff est sémantiquement correct. patch --fuzz=3 applique, puis ré-export
    canonique via git diff — même contrat que apply_and_export_debug."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        f = tdp / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(original)
        subprocess.run(["git", "-C", td, "init", "-q"], check=False, capture_output=True)
        subprocess.run(["git", "-C", td, "add", "-f", rel], check=False, capture_output=True)
        r = subprocess.run(["patch", "-p1", "--fuzz=3", "-s", "-i", "-"],
                           input=patch_text, capture_output=True, text=True, cwd=td, check=False)
        if r.returncode != 0:
            return None, (r.stderr or r.stdout or "patch fuzz rejected")[-300:]
        out = subprocess.run(["git", "-C", td, "diff", "--no-color", "--no-ext-diff", "--", rel],
                             check=False, capture_output=True, text=True)
        if not out.stdout.strip():
            return None, "diff vide après patch fuzz (aucun changement net)"
        return out.stdout, ""


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
    # Le taux no-diff est celui de la QUOTA entière (tous runs confondus) :
    # les reprises sautent les slots ok → un compteur local seul serait biaisé
    # vers l'échec et déclencherait un abort faux (bug réel du 2026-08-16).
    prior_ok = prior_nd = 0
    for rf in results.glob("*/rec.json"):
        st = json.loads(rf.read_text()).get("status")
        if st == "ok":
            prior_ok += 1
        elif st == "no-diff":
            prior_nd += 1
    state = {"attempts": 0,
             "nodiff": prior_nd, "done": prior_ok + prior_nd,      # vue QUOTA (abort)
             "run_nodiff": 0, "run_done": 0,                            # vue run (rapport)
             "consec_errors": 0,
             "rows": []}
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
        rec_file = work / "rec.json"
        if rec_file.is_file() and json.loads(rec_file.read_text())["status"] in ("ok", "no-diff"):
            return None  # slot traité (ok) ou exhausté offline (no-diff → genfam_recover)
        work.mkdir(parents=True, exist_ok=True)
        (work / "task.json").write_text(json.dumps(
            {kk: v for kk, v in task.items() if kk != "_buggy"},
            indent=1, default=str))
        original = task["_buggy"]
        diff, diff_mode, feedback = None, None, ""
        local_calls = n_errors = 0  # local_calls = appels CONSOMMÉS par ce slot
        with lock:
            infra_paused = stop["reason"] == "infra"
        if infra_paused:
            # fenêtre en pause infra : rec cohérent, zéro appel consommé de plus
            rec = {"task": iid, "campaign": task["campaign"], "window": "gen-families-v1",
                   "author": MODEL, "slot": slot, "draw": k, "status": "budget-stopped",
                   "diff_sha256": None, "diff_mode": None,
                   "n_calls_used": window_start_calls + state["attempts"]}
            (work / "rec.json").write_text(json.dumps(rec, indent=1))
            return rec
        for attempt in (1, 2):
            if not reserve():
                break
            local_calls += 1  # décompté dès la réservation (succès OU erreur endpoint)
            try:
                g = pr.gen_patch(task, feedback)
                with lock:
                    state["consec_errors"] = 0  # un succès réinitialise la série
            except Exception as e:  # noqa: BLE001 — erreur endpoint : appel consommé = journalisé (précédent S12/S14), retry via feedback au tour suivant du slot
                with lock, log.open("a") as fh:
                    fh.write(json.dumps({
                        "ts": datetime.now(UTC).isoformat(), "window": "gen-families-v1",
                        "quota": quota, "slot": slot, "attempt": attempt, "model": MODEL,
                        "campaign": task["campaign"], "error": str(e)[:300],
                        "temperature": 0.7,
                        "calls_used_window": window_start_calls + state["attempts"],
                    }) + "\n")
                feedback = "endpoint error on previous call; retry"
                n_errors += 1
                with lock:
                    state["consec_errors"] += 1
                    if state["consec_errors"] >= INFRA_STOP and not stop["reason"]:
                        stop["reason"] = "infra"  # PAUSE, pas abort : reprise watchdog
                continue
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
            edited = pr.extract_full_file(g["raw_reply"])
            this_diff, _err, raw = None, "", None
            if (edited and edited.strip() != original.strip()
                    and len(edited.splitlines()) >= len(original.splitlines()) * 0.5):
                this_diff = pr.make_diff(original, edited, task["target"])
            if this_diff is None:
                raw = pr.extract_diff_sanitized(g["raw_reply"])
                if raw:
                    this_diff, _err = pr.apply_and_export_debug(original, raw + "\n", task["target"])
                    if this_diff is None:
                        this_diff, _err2 = apply_fuzz_reexport(original, raw + "\n", task["target"])
                        if this_diff:
                            diff_mode = "fuzz-reexport"
            if this_diff:
                diff = this_diff
                if diff_mode is None:
                    diff_mode = "whole-file" if edited else "strict-git"
                break
            feedback = _err if raw else \
                "no parseable diff found in your reply (must contain one ```diff block)"
        if local_calls == 0:
            rec = {"task": iid, "campaign": task["campaign"], "window": "gen-families-v1",
                   "author": MODEL, "slot": slot, "draw": k, "status": "budget-stopped",
                   "diff_sha256": None, "diff_mode": None,
                   "n_calls_used": window_start_calls + state["attempts"]}
            (work / "rec.json").write_text(json.dumps(rec, indent=1))
            return rec  # jamais compté dans done/nodiff : aucun appel n'a eu lieu
        if diff:
            status = "ok"
        elif n_errors == local_calls:
            status = "endpoint-error"  # aucun appel n'a produit de réponse valide :
            # c'est une perte d'infra, pas un échec du modèle → hors taux no-diff,
            # retenté à la prochaine reprise (les appels restent comptés au cap)
        else:
            status = "no-diff"
        rec = {"task": iid, "campaign": task["campaign"], "window": "gen-families-v1",
               "author": MODEL, "slot": slot, "draw": k, "status": status,
               "diff_mode": diff_mode,
               "diff_sha256": sha256(diff.encode()).hexdigest() if diff else None,
               "n_calls_used": window_start_calls + state["attempts"]}
        (work / "rec.json").write_text(json.dumps(rec, indent=1))
        if diff:
            (work / "diff.patch").write_text(diff)
        with lock:
            state["rows"].append(rec)
            if status == "endpoint-error":
                return rec  # hors décompte done/nodiff : taux no-diff = échecs du modèle seulement
            state["done"] += 1; state["run_done"] += 1
            if not diff:
                state["nodiff"] += 1; state["run_nodiff"] += 1
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
    if stop["reason"] == "infra":
        (results / "summary.json").write_text(json.dumps({
            "window": "gen-families-v1", "quota": quota, "aborted": "infra-pause",
            "consec_errors": state["consec_errors"], "calls_used": calls, "cap": cap,
            "note": f"{INFRA_STOP}+ erreurs endpoint consécutives : l'endpoint auteur est "
                    "instable/mort — fenêtre PAUSÉE pour protéger l'enveloppe (les appels "
                    "d'erreur restent comptés et journalisés). Reprise par watchdog à "
                    "2×HEALTHY (rétro épic 10 item 1)."}, indent=1))
        raise SystemExit(f"PAUSE INFRA {quota}: {state['consec_errors']} erreurs endpoint "
                         f"consécutives — fenêtre pausée, budget protégé ({calls}/{cap})")
    if stop["reason"] == "cap":
        _check_budget_midway(calls, cap, results)
    if stop["reason"] == "no-diff":
        (results / "summary.json").write_text(json.dumps({
            "window": "gen-families-v1", "quota": quota, "aborted": "no-diff>60%",
            "no_diff_rate": round(stop["rate"], 3), "done": done,
            "diagnosis_needed": "sanitize/extraction regression check (règle d'abort du window)"}, indent=1))
        raise SystemExit(f"HALT {quota}: no-diff rate {stop['rate']:.0%} > 60 % après {done} slots — diagnostic requis, fenêtre stoppée (disclosé, S14)")
    (results / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in state["rows"]))
    modes = {}
    for r in state["rows"]:
        key = r.get("diff_mode") or r["status"]
        modes[key] = modes.get(key, 0) + 1
    (results / "summary.json").write_text(json.dumps({
        "quota": quota, "slots_done": state["run_done"], "no_diff": state["run_nodiff"],
        "window_slots_done": done, "window_no_diff": nodiff,
        "window_no_diff_rate": round(nodiff / done, 4) if done else None,
        "calls_used": calls, "cap": cap, "window": "gen-families-v1", "diff_modes": modes,
        "note": "diff_mode fuzz-reexport = diff récupéré par patch --fuzz + ré-export git "
                "(lignage sanitize 3516b5e) ; les slots no-diff restants sont exhaustés "
                "offline par genfam_recover.py, jamais par de nouveaux appels"}, indent=1))
    return {"quota": quota, "slots_done": state["run_done"],
            "no_diff": state["run_nodiff"],
            "window_slots_done": done, "window_no_diff": nodiff,
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
