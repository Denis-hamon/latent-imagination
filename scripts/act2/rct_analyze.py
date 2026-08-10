#!/usr/bin/env python3
"""RCT WM-context — analyse appariée (McNemar exact) A / B0 / B1.

Entrées (après exécution node) :
  - arm A  : data/landing/act2-pilot/results/{task}-off/run-result.json   (draw-3)
  - arms b0/b1 : data/landing/act2-pilot/rct-v1/results/{task}-{b0,b1}/run-result.json

Mesure primaire (ITT, décidée 2026-08-10 avant consultation des outcomes) :
slot sans candidat (pas de patch.diff à la génération) = échec F2P — sinon
l'analyse masquerait un effet du contexte sur la génération elle-même.
Sensibilité : complete-case (paires où les deux arms ont un run-result).
McNemar exact par tâche, publié quel que soit le signe (rct-prereg-v1 + amd 1-5).
Sortie : rct-v1/analysis.json + table.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
RCT = PILOT / "rct-v1"


def load_outcome(d: Path, itt: bool = True) -> bool | None:
    f = d / "run-result.json"
    if not f.is_file():
        return False if itt else None
    r = json.loads(f.read_text())
    return bool(r.get("f2p_pass"))


def mcnemar(a: list, b: list) -> dict:
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    bc = sum(1 for x, y in pairs if x and not y)   # A passe, B rate
    cc = sum(1 for x, y in pairs if not x and y)   # A rate, B passe
    n = bc + cc
    p = (2 * min(sum(math.comb(n, i) for i in range(0, min(bc, cc) + 1)),
                 sum(math.comb(n, i) for i in range(max(bc, cc), n + 1)))
         / 2 ** n) if n else 1.0
    return {"n_paired": len(pairs), "a_only": bc, "b_only": cc, "p_exact": min(1.0, p),
            "a_rate": sum(x for x, _ in pairs) / max(1, len(pairs)),
            "b_rate": sum(y for _, y in pairs) / max(1, len(pairs))}


def main() -> int:
    tasks = json.loads((PILOT / "pilot-tasks-frozen32.json").read_text())
    keys = [t["instance_id"].replace("/", "_") for t in tasks]
    # ITT primaire (None → False) ; complete-case en sensibilité
    A_itt = [load_outcome(PILOT / "results" / f"{k}-off") for k in keys]
    B0_itt = [load_outcome(RCT / "results" / f"{k}-b0") for k in keys]
    B1_itt = [load_outcome(RCT / "results" / f"{k}-b1") for k in keys]
    A_cc = [load_outcome(PILOT / "results" / f"{k}-off", itt=False) for k in keys]
    B0_cc = [load_outcome(RCT / "results" / f"{k}-b0", itt=False) for k in keys]
    B1_cc = [load_outcome(RCT / "results" / f"{k}-b1", itt=False) for k in keys]

    out = {"panel": "frozen32", "policy": {"primary": "ITT (no-candidate = F2P fail)",
                                            "sensitivity": "complete-case"},
           "itt": {"A_rate": sum(A_itt) / len(A_itt), "B0_rate": sum(B0_itt) / len(B0_itt),
                   "B1_rate": sum(B1_itt) / len(B1_itt),
                   "B1_vs_B0": mcnemar(B0_itt, B1_itt),
                   "B1_vs_A": mcnemar(A_itt, B1_itt),
                   "B0_vs_A": mcnemar(A_itt, B0_itt)},
           "complete_case": {"n_pairs_B1_B0": sum(1 for x, y in zip(B0_cc, B1_cc)
                                                  if x is not None and y is not None),
                             "B1_vs_B0": mcnemar(B0_cc, B1_cc),
                             "B1_vs_A": mcnemar(A_cc, B1_cc)}}
    (RCT / "analysis.json").write_text(json.dumps(out, indent=1))

    itt = out["itt"]
    print(f"\n===== RCT résultat — ITT (primaire), n={len(A_itt)} tâches =====")
    print(f"taux F2P : A {itt['A_rate']:.3f} | B0 {itt['B0_rate']:.3f} | B1 {itt['B1_rate']:.3f}")
    for cmp_, m in (("B1 vs B0", itt["B1_vs_B0"]), ("B1 vs A ", itt["B1_vs_A"]),
                    ("B0 vs A ", itt["B0_vs_A"])):
        print(f"{cmp_} | F2P {m['a_rate']:.3f} vs {m['b_rate']:.3f} | "
              f"discordances {m['a_only']}/{m['b_only']} | p={m['p_exact']:.3f}")
    cc = out["complete_case"]
    print(f"sensibilité complete-case : n_pairs={cc['n_pairs_B1_B0']} "
          f"(B1 vs B0 : {cc['B1_vs_B0']['a_rate']:.3f} vs {cc['B1_vs_B0']['b_rate']:.3f}, "
          f"p={cc['B1_vs_B0']['p_exact']:.3f})")
    print(f"artefact : {RCT / 'analysis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
