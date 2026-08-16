#!/usr/bin/env python3
"""Story 10.2 — poison-check genfam : LOAO ext-only du quota AVANT tout mix.

Protocole (règle S11 gelée par le window gen-families-v1) :
  chaque quota est mesuré ext-only AVANT mix dans le pool ;
  AUC < 0.65 ⇒ le quota reste HORS du pool, archivé pour étude.

Géométrie goal-free (les lignes genfam sont goal_free=True) : score = feature
LOAO-F1 = d(négatif le plus proche) − d(positif le plus proche), propre tâche
exclue des voisins (les 2 tirages d'une même tâche sont corrélés — s11.
_loao_f1_features, la même fonction qui a calibré v9). AUC = Mann-Whitney
(s11.auc).

Contrôle positif d'échelle : la MÊME métrique sur le pool v9 servi (ancrage :
la géométrie qui sert en production). On ne compare pas à un chiffre absolu
d'une autre ère (v6-GOLD-énergie 0.822) mais à la métrique identique.

Run: uv run python scripts/act2/genfam_poison_check.py --quota q1
"""
from __future__ import annotations

import argparse
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

POISON_AUC = 0.65
POISON_CLASS_MIN = 5  # règle scellée fenêtres croissance : une classe < 5 lignes
# ⇒ gate DÉGÉNÉRÉE (indéfini ≠ conforme, précédents flywheel-v10 / coverage-ts) ;
# l'AUC reste calculée si définie à titre descriptif, jamais certificatoire.

def _loao_auc(npz_path: Path, rows: list[dict]) -> tuple[float, int, int]:
    # Dégénérescence pré-déclarée (fenêtres gen-families & coverage-ts) : une
    # classe vide ⇒ AUC indéfinie ⇒ float("nan"), jamais un chiffre inventé.
    d = np.load(npz_path)
    y = np.array([int(r["y"]) for r in rows])
    n_pos, n_neg = int((y == 1).sum()), int((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan"), n_pos, n_neg  # mono-classe : AUC indéfinie
    cd = s11.norm(d["E_diff"].astype(np.float32))
    tasks = np.array([r["task"] for r in rows])
    f1 = s11._loao_f1_features(cd, tasks, y)
    # f1 = d(neg-voisin) − d(pos-voisin) ; f1 grand = la ligne ressemble aux succès
    # (convention identique à la calibration v9)
    pos, neg = f1[y == 1], f1[y == 0]
    return s11.auc(pos, neg), n_pos, n_neg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quota", default="q1")
    ap.add_argument("--dir", default=None)
    args = ap.parse_args()
    cdir = args.dir or f"genfam-{args.quota}"
    q = PILOT / cdir
    npz, rows_f = q / f"{cdir}-embed.npz", q / f"{cdir}-rows.json"
    if not npz.is_file():
        print("embed absent — lancer genfam_embed.py sur le node d'abord")
        return 1
    rows = json.loads(rows_f.read_text())
    auc_ext, n_pos, n_neg = _loao_auc(npz, rows)

    # contrôle positif : même métrique sur le pool servi v9
    v9_npz, v9_json = PILOT / "latent-pool-v9.npz", PILOT / "latent-pool-v9.json"
    control = None
    if v9_npz.is_file() and v9_json.is_file():
        v9rows = json.loads(v9_json.read_text())
        auc_v9, p9, n9 = _loao_auc(v9_npz, v9rows)
        control = {"pool": "v9", "auc_loao_f1": round(auc_v9, 4),
                   "n_pos": p9, "n_neg": n9,
                   "note": "même métrique (LOAO-F1 goal-free) sur le pool servi — ancrage d'échelle"}

    import math
    if math.isnan(auc_ext):
        gate = ("DÉGÉNÉRÉE (classe manquante — AUC indéfinie : quota archivé, "
                "NON mixé, règle scellée « indéfini ≠ conforme »)")
    elif min(n_pos, n_neg) < POISON_CLASS_MIN:
        gate = (f"DÉGÉNÉRÉE (classe min {min(n_pos, n_neg)} < {POISON_CLASS_MIN} — "
                "AUC non certificatoire, quota archivé, NON mixé, règle scellée)")
    else:
        gate = "PASS" if auc_ext >= POISON_AUC else "POISON (quota HORS pool, archivé)"
    report = {
        "quota": args.quota, "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "metric": "LOAO-F1 ext-only, AUC Mann-Whitney, propre tâche exclue",
        "n_rows": len(rows), "n_pos": n_pos, "n_neg": n_neg,
        "pos_rate_wilson95": list(s11.wilson(n_pos, n_pos + n_neg)),
        "auc_ext_only": round(auc_ext, 4),
        "gate": POISON_AUC, "verdict": gate,
        "positive_control": control,
        "rule": "règle S11 gelée : AUC ext-only < 0.65 ⇒ quota exclu du mix, archivé pour étude",
    }
    out = q / f"poison-check-{cdir}.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"AUC ext-only {args.quota}: {auc_ext:.4f} (gate {POISON_AUC}) → {gate}")
    if control:
        print(f"contrôle pool v9 (même métrique): {control['auc_loao_f1']}")
    print(f"→ {out.relative_to(ROOT)}")
    import math
    return 0 if (not math.isnan(auc_ext) and auc_ext >= POISON_AUC) else 2


if __name__ == "__main__":
    sys.exit(main())
