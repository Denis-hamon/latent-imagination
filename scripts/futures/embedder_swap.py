#!/usr/bin/env python3
"""Bras scellé embedder-swap (prereg a0d799d4) — ré-embed pooled2 avec
Qwen3-Embedding-8B via OVH AI Endpoints, MÊMES textes que le protocole
unixcoder (state=problem[:1200]+f2p, diff=diff.patch, goal=zéro), puis mesure
LOAO-F1 ext-only + bootstrap CI, et contrôle d'échelle unixcoder recalculé
dans le même run. Token lu depuis l'env OVH_AI_ENDPOINTS_TOKEN, jamais loggé.
Run: uv run python scripts/futures/embedder_swap.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
OUT = PILOT / "embedder-swap-qwen3-pooled2"
API = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/embeddings"
MODEL = "Qwen3-Embedding-8B"
BATCH = 16

_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)


def load_texts() -> tuple[list[dict], list[str], list[str]]:
    rows = json.loads((PILOT / "coverage-ts-pooled2" / "coverage-ts-pooled2-rows.json").read_text())
    stagings = {}
    states, diffs = [], []
    for r in rows:
        win = r["window"]
        camp = {"coverage-ts-v6": "coverage-ts-6"}.get(win, win)
        if camp not in stagings:
            sf = PILOT / camp / "staging-extract.json"
            st = json.loads(sf.read_text())
            stagings[camp] = {t["instance_id"]: t for t in st["tasks"]}
        task = stagings[camp].get(r["task"])
        if task is None:
            raise SystemExit(f"ABORT: tâche introuvable dans staging {camp}: {r['task']}")
        dp = PILOT / camp / "gen-results" / r["slot"] / "diff.patch"
        if not dp.is_file():
            raise SystemExit(f"ABORT: diff absent {camp}/{r['slot']}")
        states.append(task["problem"][:1200] + "\n" + "; ".join(map(str, task["f2p"][:6])))
        diffs.append(dp.read_text())
    return rows, states, diffs


def ovh_embed(texts: list[str]) -> np.ndarray:
    token = os.environ.get("OVH_AI_ENDPOINTS_TOKEN")
    if not token:
        raise SystemExit("ABORT: OVH_AI_ENDPOINTS_TOKEN absent de l'environnement")
    vecs = []
    for i in range(0, len(texts), BATCH):
        chunk = texts[i:i + BATCH]
        body = json.dumps({"model": MODEL, "input": chunk})
        last_err = None
        for attempt in range(4):
            r = subprocess.run(["curl", "-sS", "--max-time", "300", "-X", "POST", API,
                                "-H", "Content-Type: application/json",
                                "-H", f"Authorization: Bearer {token}",
                                "--data-binary", body], capture_output=True, text=True, check=False)
            if r.returncode == 0 and r.stdout.strip():
                try:
                    j = json.loads(r.stdout)
                    data = j.get("data")
                    if data:
                        vecs.extend([d["embedding"] for d in sorted(data, key=lambda x: x["index"])])
                        last_err = None
                        break
                    last_err = json.dumps(j)[:200]
                except Exception as e:  # noqa: BLE001
                    last_err = f"parse: {e} :: {r.stdout[:120]}"
            else:
                last_err = f"rc={r.returncode} {r.stderr[:120]}"
            time.sleep(2 ** attempt * 3)
        if last_err:
            raise SystemExit(f"ABORT: API OVH en échec après retries: {last_err}")
        print(f"  batch {i // BATCH + 1}/{(len(texts) + BATCH - 1) // BATCH} OK", flush=True)
    return np.array(vecs, dtype=np.float32)


def measure(E: np.ndarray, rows: list[dict], name: str) -> dict:
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    cd = s11.norm(E.astype(np.float32))
    f1 = s11._loao_f1_features(cd, tasks, y)
    pos, neg = f1[y == 1], f1[y == 0]
    auc0 = s11.auc(pos, neg)
    rng = np.random.default_rng(20260816)
    aucs = [s11.auc(rng.choice(pos, len(pos), replace=True), rng.choice(neg, len(neg), replace=True))
            for _ in range(2000)]
    lo, hi = np.percentile(aucs, [2.5, 97.5])
    print(f"{name}: AUC={auc0:.4f} IC95=[{lo:.4f},{hi:.4f}] p(<0.60)={np.mean(np.array(aucs) < 0.60):.3f}")
    return {"name": name, "auc": round(float(auc0), 4), "ic95": [round(float(lo), 4), round(float(hi), 4)],
            "p_below_0_60": round(float(np.mean(np.array(aucs) < 0.60)), 4)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, states, diffs = load_texts()
    print(f"{len(rows)} lignes pooled2 reconstruites (state {len(states)}, diff {len(diffs)})")
    # contrôle d'échelle : unixcoder recalculé AVANT l'appel API (mêmes npz)
    d0 = np.load(PILOT / "coverage-ts-pooled2" / "coverage-ts-pooled2-embed.npz")
    ctrl = measure(d0["E_diff"], rows, "unixcoder (contrôle)")
    assert abs(ctrl["auc"] - 0.6739) < 0.001, "drift contrôle unixcoder !"  # erratum a0d799d4: baseline pooled2
    # embeddings OVH
    print("embed STATE via OVH…")
    E_s = ovh_embed(states)
    print("embed DIFF via OVH…")
    E_d = ovh_embed(diffs)
    E_g = np.zeros((len(rows), E_s.shape[1]), dtype=np.float32)
    np.savez_compressed(OUT / "qwen3-pooled2-embed.npz", E_state=E_s, E_diff=E_d, E_goal=E_g)
    (OUT / "rows.json").write_text(json.dumps([{k: r.get(k) for k in
        ("task", "slot", "family", "window", "y", "goal_free")} for r in rows], indent=1) + "\n")
    swap = measure(E_d, rows, f"{MODEL} (E_diff)")
    swap_sd = measure(s11.norm(s11.norm(E_s) + s11.norm(E_d)), rows, f"{MODEL} (state+diff, descriptif)")
    grid = ("PROMOUVABLE (AUC>=0.65 ET IC95 exclut 0.60)"
            if swap["auc"] >= 0.65 and swap["ic95"][0] > 0.60
            else "CLOS (unixcoder confirmé)")
    report = {"arm": "embedder-swap-qwen3-embedding-8b", "prereg_anchor": "a0d799d4",
              "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
              "model": MODEL, "api": "OVH AI Endpoints oai.endpoints.kepler.ai.cloud.ovh.net",
              "dim": int(E_s.shape[1]), "n_rows": len(rows),
              "texts": "identiques au protocole unixcoder (state=problem[:1200]+f2p[:6], diff=diff.patch, goal=0)",
              "control_unixcoder": ctrl, MODEL: {"ediff": swap, "state_plus_diff": swap_sd},
              "grille_decision": grid,
              "disclosure": "pooling API (Qwen3 default) != CLS unixcoder — différence de protocole notée, textes identiques"}
    (OUT / "embedder-swap-report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"\nDÉCISION GRILLE : {grid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
