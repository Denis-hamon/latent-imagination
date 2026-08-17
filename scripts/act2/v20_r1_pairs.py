#!/usr/bin/env python3
"""v20 R1 (587993051b8dcc51) — précision par paire INTRA-TICKET sur l'énergie
goal. Produit réel : deux candidats du même ticket, y opposés : le y=1
doit avoir l'énergie la plus basse. Node (cache v18)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"


def norm(A):
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def main() -> int:
    rows = json.loads((PILOT / "ts-gold-v18" / "v18-rows.json").read_text())
    d = np.load(PILOT / "ts-gold-v18" / "v18-rows.emb.npz")
    Es, Ed, Eg = d["Es"], d["Ed"], d["Eg"]
    y = np.array([r["y"] for r in rows])
    tasks = np.array([r["task"] for r in rows])
    cd, cg = norm(norm(Es) + norm(Ed)), norm(norm(Es) + norm(Eg))
    e = 1.0 - (cd * cg).sum(-1)
    n_pair, win = 0, 0
    per_ticket_pairs = {}
    for t in sorted(set(tasks)):
        ix = np.where(tasks == t)[0]
        if len(ix) < 2:
            continue
        for a in range(len(ix)):
            for b in range(a + 1, len(ix)):
                i, j = ix[a], ix[b]
                if y[i] == y[j]:
                    continue
                n_pair += 1
                ok = e[i] < e[j] if y[i] == 1 else e[j] < e[i]
                tie = abs(float(e[i] - e[j])) < 1e-12
                win += 1 if ok else (0.5 if tie else 0)
                per_ticket_pairs[t] = per_ticket_pairs.get(t, 0) + 1
    acc = win / n_pair if n_pair else 0.0
    rng = np.random.default_rng(20260817)
    wins = []
    for t in sorted(set(tasks)):
        ix = np.where(tasks == t)[0]
        es_t, ys_t = e[ix], y[ix]
        for a in range(len(ix)):
            for b in range(a + 1, len(ix)):
                if ys_t[a] != ys_t[b]:
                    ok = es_t[a] < es_t[b] if ys_t[a] == 1 else es_t[b] < es_t[a]
                    wins.append(1.0 if ok else 0.0)
    wins = np.array(wins)
    boots = [float(rng.choice(wins, len(wins), replace=True).mean()) for _ in range(2500)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    r1_ok = bool(acc >= 0.60 and n_pair >= 150 and lo >= 0.55)
    out = {"R1": {"n_paires_intra_ticket": int(n_pair),
                  "n_tickets_avec_paires_mixtes": int(np.sum([v > 0 for v in per_ticket_pairs.values()])),
                  "acc_paire": round(float(acc), 4),
                  "ic95_bootstrap2500": [round(float(lo), 4), round(float(hi), 4)],
                  "grille": "acc>=0.60 ET paires>=150 ET IC bas>=0.55", "ok": r1_ok},
           "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    print(json.dumps(out, indent=1))
    (PILOT / "v20-R1-paires.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0 if r1_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
