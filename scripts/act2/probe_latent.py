#!/usr/bin/env python3
"""Auscultation du pool latent Act II — verification avant de tirer des conclusions.

Le contrôle le plus dur : est-ce que le succès est détectable à l'état-même (sans
diff) ? Si oui, tout ce qu'on mesure est du prétexte.
"""

import json

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

BASE = "data/landing/act2-pilot"
with open(f"{BASE}/latent-pool.json") as _fh:
    rows = json.load(_fh)
d = np.load(f"{BASE}/latent-pool.npz")
E_s, E_d, E_g, y = d["E_state"], d["E_diff"], d["E_goal"], np.array([r["y"] for r in rows])

def norm(A):
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
E_s, E_d, E_g = norm(E_s), norm(E_d), norm(E_g)

# --- Contrôle 1 : la probabilité brute sur l'ÉTAT SEUL
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict

groups = np.array([r["task"] for r in rows])
logo = LeaveOneGroupOut()
p_probe_state = cross_val_predict(LogisticRegression(max_iter=2000, class_weight="balanced"), E_s, y, groups=groups, cv=logo, method="predict_proba")[:, 1]
p_probe_diff = cross_val_predict(LogisticRegression(max_iter=2000, class_weight="balanced"), E_d, y, groups=groups, cv=logo, method="predict_proba")[:, 1]
p_probe_both = cross_val_predict(LogisticRegression(max_iter=2000, class_weight="balanced"), np.concatenate([E_s, E_d], axis=1), y, groups=groups, cv=logo, method="predict_proba")[:, 1]
def auc(sc, yy):
    s = [x for i, x in enumerate(sc) if yy[i] == 1]; f = [x for i, x in enumerate(sc) if yy[i] == 0]
    w = t = 0.0
    for a in s:
        for b in f:
            if a > b: w += 1
            elif a == b: t += 1
    return (w + 0.5 * t) / (len(s) * len(f))
print(f"AUC de l'état SEUL: {auc(p_probe_state, y):.3f}  (si >0.7, tout est prétexte)")
print(f"AUC du diff SEUL: {auc(p_probe_diff, y):.3f}")
print(f"AUC état+diff concat: {auc(p_probe_both, y):.3f}")

# --- Contrôle 2 : l'énergie latente mesure-t-elle autre chose que « identique à gold » ?
cos_dg = np.sum(norm(E_s + E_d) * norm(E_s + E_g), axis=1)
diff_vs_gold = np.sum(norm(E_d) * norm(E_g), axis=1)
state_vs_gold = np.sum(norm(E_s) * norm(E_g), axis=1)
print(f"AUC énergie(state,diff): {auc(-1 + cos_dg, y):.3f}")
print(f"AUC diff-gold seul:       {auc(-diff_vs_gold, y):.3f}")
print(f"AUC state-gold seul:      {auc(-state_vs_gold, y):.3f}  (si >0.6, leak de task)")

# --- Contrôle 3 : l'attention du gold-head récompense-t-elle les résolutions ?
ok_rows = [i for i, r in enumerate(rows) if r["y"] == 1][:3]
ko_rows = [i for i, r in enumerate(rows) if r["y"] == 0][:3]
tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
model = AutoModel.from_pretrained("microsoft/unixcoder-base").to("cuda").eval()
for name, i in [(f"succès {rows[i]['arm']}", i) for i in ok_rows] + [(f"fail {rows[i]['arm']}", i) for i in ko_rows]:
    r = rows[i]
    with torch.no_grad():
        for tag, txt in (("diff-gen", r["diff"]), ("diff-gold", r["gold"])):
            tb = tok([txt], return_tensors="pt", padding=True, truncation=True, max_length=512).to("cuda")
            o = model(**tb, output_attentions=True)
            H = o.last_hidden_state[0]
            cos_to_cls = (H * H[0]).sum(-1) / (H.norm(dim=-1) * H[0].norm() + 1e-9)
            top = cos_to_cls.argsort(descending=True)[:5].tolist()
            toks = tok.convert_ids_to_tokens(tb.input_ids[0])
            print(f"[{name}] {tag} → top-CLS-simi tokens: {[toks[j] for j in top][:5]}")

# --- Contrôle 4 : permutation des tâches (exit test)
rng = np.random.default_rng(17)
wrong = rng.permutation(len(rows))
cos_dg_perm = np.sum(norm(E_s + E_d) * norm(E_s + E_g[wrong]), axis=1)
print(f"AUC énergie avec goals permutés: {auc(-1 + cos_dg_perm, y):.3f}  (doit ≈ 0.5)")
