#!/usr/bin/env python3
"""S13 — baseline LLM-juge : Qwen3.8-2.4T-A95B-NVFP4 zero-shot sur le pool v7.

Pré-enregistré dans governance/act2/budget-v1.toml (entrée 2026-08-14 suite,
 accord owner) :
  - 177 lignes du pool v7, 1 appel par ligne (T=0) + 1 retry si parse échoue,
    cap 250 calls pour la fenêtre ;
  - entrée juge = state + diff candidat, EXACTEMENT l'information des
    instruments ; JAMAIS le gold (comparaison goal-free, déclarée) ;
  - sortie JSON {"probability": 0-100} ;
  - métriques : AUC / acc100 / cov@>=0.95 via la fonction report du harness
    s11/s12_pool, recalculs appariés GOLD v7 et GxF strict v7 sur les mêmes
    lignes ; contrôle positif v6 (0.822/0.779) recalculé en tête de run ;
  - raw persistée dès le 1er appel ; call-log jsonl avec sha256 prompt/réponse.

Aucune gate déclarée — mesure de référence. Zéro promotion.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
OUT = PILOT / "s13-judge"
RAW = OUT / "raw"
LOG = OUT / "call-log.jsonl"

MODEL = os.environ.get("S13_MODEL", "Qwen3.8-2.4T-A95B-NVFP4")
PARALLEL = int(os.environ.get("S13_PARALLEL", "4"))
CAP = int(os.environ.get("S13_CAP", "250"))

_spec = importlib.util.spec_from_file_location(
    "s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s11)
norm, wilson, auc = s11.norm, s11.wilson, s11.auc
loao_energy, gxf_loao, report = s11.loao_energy, s11.gxf_loao, s11.report

PROMPT = """You are a strict code-review judge. A bug report lists tests that currently FAIL on the buggy repository. A candidate patch (unified diff) is proposed against that buggy repository.

Estimate the probability that applying this diff fixes the bug: the listed failing tests pass AND no other behavior regresses.

Answer with ONLY a JSON object, no prose, no markdown fences:
{{"probability": <integer between 0 and 100>}}

0 = certainly does not fix (tests still fail or regression introduced). 100 = certainly fixes.

BUG REPORT AND FAILING TEST IDENTIFIERS:
{state}

CANDIDATE DIFF:
{diff}
"""

_calls_lock = threading.Lock()
_calls_window = 0
_cap_hit = False
_log_lock = threading.Lock()


def _key() -> str:
    k = os.environ.get("LI_GALERE_KEY") or os.environ.get("OPENCODE_GALERE_KEY")
    if k:
        return k
    f = Path.home() / ".local/share/opencode/auth.json"
    if f.is_file():
        return json.loads(f.read_text())["galere"]["key"]
    raise SystemExit("aucune clé galere (env ou auth opencode)")


def log_call(idx: int, attempt: int, prompt: str, reply: dict, rc_ok: bool):
    with _log_lock, LOG.open("a") as fh:
        fh.write(json.dumps({
            "ts": datetime.now(UTC).isoformat(),
            "window": "s13-judge", "row": idx, "attempt": attempt,
            "model": MODEL, "rc_ok": rc_ok,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "reply_sha256": hashlib.sha256(
                reply.get("text", "").encode()).hexdigest(),
            "usage": reply.get("usage", {}),
        }) + "\n")


def call_model(prompt: str) -> dict:
    body = json.dumps({
        "model": MODEL, "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0, "max_tokens": 32000,  # thinking non débrayable
        # (backend : "Disabling thinking is not supported") ; à 4000 puis
        # 16000 le raisonnement sature le budget et le content sort vide
        # (mesuré row 0 : reasoning convergent mais coupé à finish_reason=length)
        # → 32000, même ordre de grandeur que la ladder finding #4.
    })
    cmd = ["curl", "-sS", "--max-time", "590", "-X", "POST",
           "https://ai.galere.org/v1/chat/completions",
           "-H", "Content-Type: application/json",
           "-H", f"Authorization: Bearer {_key()}", "--data-binary", "@-"]
    p = subprocess.run(cmd, input=body.encode(), capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"curl rc={p.returncode}: {p.stderr[-300:].decode()}")
    j = json.loads(p.stdout.decode())
    if "choices" not in j:
        raise RuntimeError(f"payload: {str(j)[:300]}")
    m = j["choices"][0]["message"]
    return {"text": m.get("content") or "", "usage": j.get("usage", {})}


def parse_p(text: str) -> int | None:
    m = re.search(r'\{\s*"probability"\s*:\s*([0-9]{1,3})\s*\}', text)
    if not m:
        m = re.search(r'"probability"\s*:\s*([0-9]{1,3})', text)
    if m:
        v = int(m.group(1))
        return max(0, min(100, v))
    m = re.search(r"\b([0-9]{1,3})\b", text[-60:])
    return max(0, min(100, int(m.group(1)))) if m else None


def judge_row(idx: int, row: dict) -> dict | None:
    global _calls_window, _cap_hit
    slot = f"{idx:03d}__{row['task'].replace('/', '_')}"
    pf = RAW / f"{slot}.probability.json"
    if pf.is_file():
        return json.loads(pf.read_text())
    prompt = PROMPT.format(state=row["state"], diff=row["diff"])
    for attempt in (1, 2):
        with _calls_lock:
            if _cap_hit:
                return None
            if _calls_window >= CAP:
                _cap_hit = True
                print(f"CAP {CAP} atteint — arrêt des nouveaux calls", flush=True)
                return None
            _calls_window += 1
        p = prompt + (
            "\n\nYOUR PREVIOUS ANSWER COULD NOT BE PARSED. Reply with ONLY "
            'the JSON object: {"probability": <integer 0-100>}' if attempt == 2
            else "")
        try:
            out = call_model(p)
            ok = True
        except Exception as e:  # noqa: BLE001
            out = {"text": f"ERROR: {e}", "usage": {}}
            ok = False
        rf_a = RAW / f"{slot}.a{attempt}.txt"
        rf_a.write_text(out["text"])
        log_call(idx, attempt, p, out, ok)
        pv = parse_p(out["text"]) if ok else None
        if pv is not None:
            res = {"row": idx, "task": row["task"], "probability": pv,
                   "attempts": attempt}
            pf.write_text(json.dumps(res, indent=1))
            return res
    return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    rows6 = json.loads((PILOT / "latent-pool-v6.json").read_text())
    v7 = json.loads((PILOT / "latent-pool-v7.json").read_text())
    du6 = np.load(PILOT / "latent-pool-v6.npz")
    dv7 = np.load(PILOT / "latent-pool-v7.npz")
    y6 = np.array([int(r["y"]) for r in rows6])
    t6 = np.array([r["task"] for r in rows6])
    y7 = np.array([int(r["y"]) for r in v7])
    t7 = np.array([r["task"] for r in v7])
    camp = np.array(["v6"] * len(rows6) + ["s12"] * (len(v7) - len(rows6)))
    maj7 = max(y7.mean(), 1 - y7.mean())

    # --- contrôle positif v6, avant toute dépense ---
    EU6 = {k: norm(du6[k]) for k in ("E_state", "E_diff", "E_goal")}
    pred, conf, sco = loao_energy(norm(EU6["E_state"] + EU6["E_diff"]),
                                  norm(EU6["E_state"] + EU6["E_goal"]), y6, t6)
    ctrl = report("CTRL v6 GOLD (=S7/S10/S11)", pred, conf, sco, y6,
                  max(y6.mean(), 1 - y6.mean()))
    if not (abs(ctrl["auc"] - 0.822) < 0.01 and abs(ctrl["acc100"] - 0.779) < 0.005):
        print("contrôle positif en dérive — STOP avant dépense")
        return 1

    # --- instruments appariés sur v7 ---
    EU7 = {k: norm(dv7[k]) for k in ("E_state", "E_diff", "E_goal")}
    cd7, cg7 = norm(EU7["E_state"] + EU7["E_diff"]), norm(EU7["E_state"] + EU7["E_goal"])
    pred_gold, conf_gold, sco_gold = loao_energy(cd7, cg7, y7, t7)
    pred_g, conf_g, sco_gxf = gxf_loao(cd7, cg7, y7, t7)
    gold = report("Rappel v7 GOLD uxc", pred_gold, conf_gold, sco_gold, y7, maj7)
    gxf = report("Rappel v7 GxF strict", pred_g, conf_g, sco_gxf, y7, maj7)

    global _calls_window
    existing = sum(1 for _ in LOG.open()) if LOG.exists() else 0
    _calls_window = existing
    todo = [i for i in range(len(v7))
            if not (RAW / f"{i:03d}__{v7[i]['task'].replace('/', '_')}.probability.json").is_file()]
    print(f"pool v7 n={len(v7)} | déjà jugées {len(v7) - len(todo)} "
          f"| à faire {len(todo)} | calls fenêtre déjà loggés {existing} | cap {CAP}",
          flush=True)
    if todo:
        with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
            futs = {ex.submit(judge_row, i, v7[i]): i for i in todo}
            for done, fut in enumerate(as_completed(futs), start=1):
                r = fut.result()
                if done % 10 == 0 or r is None:
                    print(f"[{done}/{len(todo)}] row {futs[fut]} "
                          f"p={r['probability'] if r else None} "
                          f"({_calls_window} calls)", flush=True)

    # --- agrégation ---
    probs = np.full(len(v7), np.nan)
    attempts = {}
    for pf in sorted(RAW.glob("*.probability.json")):
        r = json.loads(pf.read_text())
        probs[r["row"]] = r["probability"] / 100.0
        attempts[r["row"]] = r.get("attempts", 1)
    missing = [int(i) for i in np.where(np.isnan(probs))[0]]
    if missing:
        print(f"ERREUR : {len(missing)} lignes sans score : {missing[:10]}")
        return 1
    out = {
        "model": MODEL, "n": len(v7), "majority": float(maj7),
        "calls_window_preexisting": existing,
        "recomputed_instruments": {"v7_gold": gold, "v7_gxf_strict": gxf},
    }
    pred_j = (probs > 0.5).astype(int)
    conf_j = np.abs(probs - 0.5)
    out["judge"] = report("S13 juge Qwen3.8-2.4T", pred_j, conf_j, probs,
                          y7, maj7)
    jd = out["judge"]
    print(json.dumps({"judge_auc": jd["auc"], "acc100": jd["acc100"],
                      "cov": jd["max_cov"]}, indent=1))

    # --- stratification descriptive ---
    st = {}
    for name, mask in (("lignes_v6", camp == "v6"),
                       ("lignes_s12", camp == "s12"),
                       ("positifs", y7 == 1), ("négatifs", y7 == 0)):
        pm, ym = probs[mask], y7[mask]
        if len(set(ym)) >= 2:
            st[name] = {"n": int(mask.sum()),
                        "auc": auc(pm[ym == 1], pm[ym == 0])}
        else:
            st[name] = {"n": int(mask.sum()), "mean_p": round(float(pm.mean()), 3)}
    out["strata"] = st
    for k, v in st.items():
        print(f"  {k:<12} {v}")

    # --- pairing head-to-head vs GxF strict ---
    pj = (probs > 0.5).astype(int)
    pg = (sco_gxf > 0.5).astype(int)
    both_r = int(((pj == y7) & (pg == y7)).sum())
    j_seul = int(((pj == y7) & (pg != y7)).sum())
    g_seul = int(((pj != y7) & (pg == y7)).sum())
    aucun = int(((pj != y7) & (pg != y7)).sum())
    out["pairing_vs_gxf"] = {"accord_correct": both_r, "juge_seul": j_seul,
                             "gxf_seul": g_seul, "les_deux_faux": aucun}
    print(f"pairing : accordo {both_r} | juge seul {j_seul} | gxf seul {g_seul} "
          f"| les deux faux {aucun}")

    out["attempts_hist"] = {str(v): int(sum(1 for a in attempts.values()
                                             if a == v))
                            for v in sorted(set(attempts.values()))}
    (PILOT / "s13-judge.json").write_text(json.dumps(out, indent=1))
    print(f"\nArtefact : {PILOT / 's13-judge.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
