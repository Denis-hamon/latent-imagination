#!/usr/bin/env python3
"""S11-bis — diagnostic de la déclaration POISON ext (0 call, numpy only).

Le critère poison (AUC ext-seul < 0.65) tient sur l'ensemble. Ce script
stratifie pour localiser le signal résiduel : auteurs, géométrie du diff
(mono/multi-fichier, partage d'un fichier gold, longueur), score diff↔gold
seul (recette simplifiée S10), axe F1 goal-free (recette G1).
Toute conclusion de sous-groupe est descriptive, pas un nouveau gate.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "s11", Path.home() / "latent-imagination/scripts/act2/s11_ext_pool.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

PILOT = Path.home() / "latent-imagination/data/landing/act2-pilot"
rows = json.loads((PILOT / "s11-ext-pool.json").read_text())
dx = np.load(PILOT / "s11-ext-pool.npz")

y = np.array([int(r["y"]) for r in rows])
t = np.array([r["task"] for r in rows])
EU = {k: m.norm(dx[k]) for k in ("E_state", "E_diff", "E_goal")}
cd = m.norm(EU["E_state"] + EU["E_diff"])
cg = m.norm(EU["E_state"] + EU["E_goal"])
maj = max(y.mean(), 1 - y.mean())
print(f"n={len(y)} pos={y.sum()} ({y.mean():.1%}) | maj={maj:.3f}", flush=True)

pred, conf, sco = m.loao_energy(cd, cg, y, t)
energy = 1.0 - (cd * cg).sum(-1)

def auci(s):
    return m.auc(s[y == 1], s[y == 0])

out = {"gxt_auc": auci(sco), "majority": float(maj)}
print(f"GOLD énergie (LOAO): AUC {out['gxt_auc']:.3f}", flush=True)

# --- stratifications sur le même score LOAO
def files_of(d):
    return re.findall(r"diff --git a/(\S+)", d or "")

nfiles = np.array([len(set(files_of(r["diff"]))) for r in rows])
share = np.array([r.get("x_shares_gold_file", False) for r in rows])
dlen = np.array([len(r["diff"]) for r in rows])
auth = np.array([r["author"] for r in rows])

for name, mask in [
    ("mono-fichier", nfiles == 1),
    ("multi-fichiers", nfiles > 1),
    ("2 fichiers max", nfiles <= 2),
    ("partage fichier gold", share),
    ("NE partage PAS gold", ~share),
    ("diff court (<médiane)", dlen < np.median(dlen)),
    ("diff long (>médiane)", dlen >= np.median(dlen)),
]:
    yy, ss = y[mask], sco[mask]
    if len(set(yy)) < 2:
        continue
    print(f"  {name:<28} n={mask.sum():6d} pos={yy.mean():.2f} "
          f"AUC={m.auc(ss[yy == 1], ss[yy == 0]):.3f}", flush=True)

for a in sorted(set(auth)):
    mask = auth == a
    yy, ss = y[mask], sco[mask]
    if len(set(yy)) < 2:
        continue
    print(f"  auteur {a:<32} n={mask.sum():6d} pos={yy.mean():.2f} "
          f"AUC={m.auc(ss[yy == 1], ss[yy == 0]):.3f}", flush=True)

# --- recette simplifiée S10 : diff↔gold seul (l'état n'apporte rien en v6)
sdg = (m.norm(EU["E_diff"]) * m.norm(EU["E_goal"])).sum(-1)
out["diffgold_auc"] = auci(sdg)
print(f"diff↔gold seul: AUC {out['diffgold_auc']:.3f}", flush=True)

# --- axe F1 goal-free (G1) sur ext seul
print("calcul F1 goal-free (chunks)…", flush=True)
f1 = m._loao_f1_features(cd, t, y)
out["f1_auc"] = auci(-f1)
print(f"F1 attracteur (négatif = proche des échecs): AUC {out['f1_auc']:.3f}",
      flush=True)

# --- combinaison rang GOLD + F1 (recette G1 rank-mean)
try:
    def rankdata(x):
        return np.argsort(np.argsort(x)).astype(float)
    rg = rankdata(sco) / len(sco)
    rf = rankdata(-f1) / len(f1)
    out["rank_gxf_auc"] = auci((rg + rf) / 2)
    print(f"rang-moyen GOLD+F1: AUC {out['rank_gxf_auc']:.3f}", flush=True)
except Exception as e:
    print("skip rank-mean:", e)

# --- sous-population la plus propre : mono-fichier ET partage gold
mask = (nfiles == 1) & share
yy, ss = y[mask], sco[mask]
if len(set(yy)) >= 2:
    out["clean_subset_auc"] = m.auc(ss[yy == 1], ss[yy == 0])
    out["clean_subset_n"] = int(mask.sum())
    out["clean_subset_pos"] = float(yy.mean())
    print(f"SOUS-ENSEMBLE mono-fichier∧gold n={mask.sum()} pos={yy.mean():.2f} "
          f"AUC={out['clean_subset_auc']:.3f}", flush=True)

out["strata_done"] = True
json.dump(out, open(PILOT / "s11-diag.json", "w"), indent=1)
print(f"OK {PILOT / 's11-diag.json'}", flush=True)
