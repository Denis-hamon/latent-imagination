#!/usr/bin/env python3
"""Extension S13 — juge les lignes ajoutées à v8 (rows 177..206), même fenêtre,
même protocole (T=0, 1 retry parse), dans le cap pré-enregistré de 250 calls.
Réutilise la mécanique de s13_llm_judge ; n'écrit PAS l'artefact global.
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"

spec = importlib.util.spec_from_file_location("s13", ROOT / "scripts/act2/s13_llm_judge.py")
s13 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s13)

v8 = json.loads((PILOT / "latent-pool-v8.json").read_text())
s13.RAW.mkdir(parents=True, exist_ok=True)
existing = sum(1 for _ in s13.LOG.open()) if s13.LOG.exists() else 0
s13._calls_window = existing
print(f"calls déjà loggés fenêtre S13 : {existing} | cap {s13.CAP}", flush=True)

todo = [i for i in range(len(v8))
        if not (s13.RAW / f"{i:03d}__{v8[i]['task'].replace('/', '_')}.probability.json").is_file()]
print(f"à juger : {len(todo)}", flush=True)

from concurrent.futures import ThreadPoolExecutor, as_completed
with ThreadPoolExecutor(max_workers=s13.PARALLEL) as ex:
    futs = {ex.submit(s13.judge_row, i, v8[i]): i for i in todo}
    done = 0
    for fut in as_completed(futs):
        r = fut.result(); done += 1
        print(f"[{done}/{len(todo)}] row {futs[fut]} "
              f"p={r['probability'] if r else None} ({s13._calls_window} calls)", flush=True)

# AUC juge sur les nouvelles lignes seulement
import importlib.util as iu
sp = iu.spec_from_file_location("s11", ROOT / "scripts/act2/s11_ext_pool.py")
s11 = iu.module_from_spec(sp); sp.loader.exec_module(s11)
import numpy as np
probs, ys = [], []
for i in todo:
    pf = s13.RAW / f"{i:03d}__{v8[i]['task'].replace('/', '_')}.probability.json"
    if pf.is_file():
        r = json.loads(pf.read_text())
        probs.append(r["probability"] / 100.0); ys.append(int(v8[i]["y"]))
probs = np.array(probs); ys = np.array(ys)
if len(set(ys)) == 2:
    print(f"\nAUC juge sur {len(ys)} nouvelles lignes : "
          f"{s11.auc(probs[ys==1], probs[ys==0]):.3f} (pos {ys.sum()})")
print("OK extension S13")
