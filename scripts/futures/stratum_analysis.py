#!/usr/bin/env python3
"""Arm mondrian-metric (prereg 80fd6523) — le plateau global est-il un
artefact de métrique ? AUC globale vs intra-famille vs stratifiée pondérée
sur pooled7 (zéro appel).
Run: uv run python scripts/futures/stratum_analysis.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)

N_MIN_STRATUM = 12


def main() -> int:
    rows = json.loads((PILOT / "pooled7" / "pooled7-rows.json").read_text())
    d = np.load(PILOT / "pooled7" / "pooled7-embed.npz")
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    fams = np.array([r.get("family") or "inconnu" for r in rows])
    cd = s11.norm(d["E_diff"].astype(np.float32))

    f1_all = s11._loao_f1_features(cd, tasks, y)
    auc_global = s11.auc(f1_all[y == 1], f1_all[y == 0])
    print(f"CONTRÔLE globale : AUC={auc_global:.4f} (attendu 0.6946)")

    intra, small = [], []
    for fam in sorted(set(fams)):
        idx = np.where(fams == fam)[0]
        n = len(idx)
        if n < N_MIN_STRATUM:
            small.append((fam, n, int(y[idx].sum()), int((1 - y[idx]).sum())))
            continue
        yy, tt = y[idx], tasks[idx]
        if yy.sum() == 0 or yy.sum() == n:
            intra.append({"famille": fam, "n": n, "pos": int(yy.sum()), "neg": int(n - yy.sum()),
                          "auc": None, "statut": "mono-classe (AUC indéfinie)"})
            continue
        f1 = s11._loao_f1_features(cd[idx], tt, yy)
        auc = s11.auc(f1[yy == 1], f1[yy == 0])
        intra.append({"famille": fam, "n": n, "pos": int(yy.sum()), "neg": int(n - yy.sum()),
                      "auc": round(float(auc), 4)})
    valid = [s for s in intra if s.get("auc") is not None]
    wsum = sum(s["n"] for s in valid)
    strat = sum(s["auc"] * s["n"] for s in valid) / max(1, wsum) if valid else float("nan")
    print(f"\nINTRA-FAMILLE (n >= {N_MIN_STRATUM}) :")
    for s in intra:
        print(f"  {s['famille']:32} n={s['n']:3} ({s['pos']}+/{s['neg']}-) AUC={s.get('auc') if s.get('auc') is not None else 'DEFINI-NON'}")
    print(f"\nAUC STRATIFIÉE pondérée : {strat:.4f} (sur {len(valid)} familles, {wsum} lignes)")
    print(f"AUC globale             : {auc_global:.4f}")
    print(f"DELTA stratifiée-globale: {strat - auc_global:+.4f} (grille gelée : >= +0.05 => artefact de métrique)")
    print(f"\nfamilles < {N_MIN_STRATUM} (descriptif, non agrégées) : {len(small)} familles, {sum(x[1] for x in small)} lignes")
    report = {"arm": "mondrian-metric-awareness", "prereg": "80fd6523",
              "population": {"name": "pooled7", "n": len(rows)},
              "auc_globale": round(float(auc_global), 4),
              "auc_stratifiee": round(float(strat), 4),
              "delta": round(float(strat - auc_global), 4),
              "grille": "artefact-metrique CONFIRMÉ" if (strat - auc_global) >= 0.05 else
                        "plateau REPRÉSENTATION confirmé (delta < +0.05)",
              "intra": intra, "petites_familles_nb": len(small),
              "strates_conformables_projetees": len([s for s in intra if s.get("neg", 0) >= 5 or s.get("pos", 0) >= 5]),
              "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    (ROOT / "governance" / "act2" / "arm-artifacts" / "mondrian-metric-analysis-2026-08-17.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"\nVERDICT GRILLE : {report['grille']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
