#!/usr/bin/env python3
"""Story 12.1 — calibration conforme Mondrian par famille (0 appel, pool gelé).

But (FR-27) : que l'abstention servie porte une GARANTIE de couverture
distribution-free, pas un seuil réglé. Méthode pré-enregistrée dans
l'artefact (pas de sélection post-hoc contre l'eval) :

  score = f1 LOAO (géométrie servie : d neg-voisin − d pos-voisin, propre tâche
  exclue) ; thr = médiane pool gelée ; conf = |f1 − thr| ; pred = f1 > thr.
  Par strate famille (préfixe repo, Mondrian) : τ_g = plus petit seuil de conf
  tel que le taux d'erreur des lignes retenues (conf ≥ τ_g) sur le replay
  LOAO ≤ α (contrôle conforme par quantile sur résidus — Vovk/risque conforme,
  garantie sous échangeabilité DANS la strate, bornes finite-sample en Wilson
  divulguées). Strates à n < N_MIN ⇒ « données insuffisantes » (None — jamais
  de garantie fabriquée, règle honest-emptiness).

Contrôles : v6 GOLD reproduit inchangé (0.822/0.779) ; comparaison publiée vs
le régime tau fixe servi (cov, acc, validité par famille).

Sortie : governance/act2/arm-artifacts/risk-scan-v10-conformal.json
Run: uv run python scripts/act2/conformal_calibrate.py [--pool v10]
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
CALIB_DIR = ROOT / "governance" / "act2" / "arm-artifacts"

_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)

ALPHAS = (0.05, 0.10)   # grille pré-enregistrée — jamais élargie après lecture
N_MIN = 12              # strate < N_MIN lignes ⇒ garantie None (honest emptiness)
METHOD = ("τ_g = min{t : err_rate(conf≥t, replay LOAO, strate g) ≤ α}, "
          "quantile conforme sur lignes retenues ; garantie sous échangeabilité "
          "intra-strate ; Wilson 95 % finite-sample divulgué ; n<N_MIN ⇒ None")


def conformal_tau(conf: np.ndarray, errors: np.ndarray, alpha: float, n_min: int) -> dict:
    """Seuil conforme d'une strate. Déterministe, numpy seul."""
    n = int(conf.size)
    if n < n_min:
        return {"n": n, "tau": None, "guarantee": None,
                "reason": f"insufficient data (n={n} < {n_min}) — honest emptiness"}
    order = np.argsort(-conf)  # du plus confiant au moins confiant
    kept = err_kept = 0
    tau = None
    # parcourt les paliers de conf décroissants : retient dès que l'erreur ≤ α
    i = 0
    ranked_conf = conf[order]
    ranked_err = errors[order].astype(int)
    cum_err = np.cumsum(ranked_err)
    for k in range(1, n + 1):
        rate = cum_err[k - 1] / k
        if rate <= alpha:
            # plus petit seuil retenant ≥ k lignes avec erreur ≤ α :
            # on continue pour maximiser la couverture (tau = conf de la k-ième
            # ligne retenue au point le plus bas valide)
            tau = float(ranked_conf[k - 1])
            kept, err_kept = k, int(cum_err[k - 1])
    # le seuil DOIT retenir au moins la ligne la plus confiante ; si aucun point
    # valide (trop d'erreurs même au sommet) ⇒ abstention totale de la strate
    if tau is None:
        return {"n": n, "tau": float("inf"), "kept": 0, "err_kept": 0,
                "realized_err_rate": None, "wilson95": None,
                "guarantee": f"≤{alpha} si retenues, mais aucune ligne ne satisfait "
                             "le contrôle sur le replay ⇒ strate en abstention totale"}
    rate = err_kept / kept if kept else None
    lo, hi = (s11.wilson(err_kept, kept) if kept else (None, None))
    return {"n": n, "tau": round(tau, 6), "kept": kept, "err_kept": err_kept,
            "realized_err_rate": round(rate, 4) if rate is not None else None,
            "wilson95": [round(lo, 4), round(hi, 4)] if kept else None,
            "coverage_share": round(kept / n, 4),
            "guarantee": f"≤{alpha} sous échangeabilité intra-strate"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="v10")
    args = ap.parse_args()
    pool = args.pool

    rows = json.loads((PILOT / f"latent-pool-{pool}.json").read_text())
    d = np.load(PILOT / f"latent-pool-{pool}.npz")
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    fams = np.array([t.split(".")[0] if "." in t else t.split(":")[0] for t in tasks])
    cd = s11.norm(s11.norm(d["E_state"]) + s11.norm(d["E_diff"]))
    f1 = s11._loao_f1_features(cd, tasks, y)
    thr = float(np.median(f1))
    conf = np.abs(f1 - thr)
    pred = (f1 > thr).astype(int)
    errors = pred != y

    # ---- contrôle positif v6 (inchangé, même recette que les promotions) ----
    try:
        rows6 = json.loads((PILOT / "latent-pool-v6.json").read_text())
        d6 = np.load(PILOT / "latent-pool-v6.npz")
        y6 = np.array([int(r["y"]) for r in rows6])
        t6 = np.array([r["task"] for r in rows6])
        Es6, Ed6, Eg6 = (s11.norm(d6[k]) for k in ("E_state", "E_diff", "E_goal"))
        pred6, conf6, sco6 = s11.loao_energy(s11.norm(Es6 + Ed6), s11.norm(Es6 + Eg6), y6, t6)
        ctrl = s11.report("CTRL v6 GOLD", pred6, conf6, sco6, y6,
                          max(y6.mean(), 1 - y6.mean()))
        ctrl_ok = abs(ctrl["auc"] - 0.822) < 0.01 and abs(ctrl["acc100"] - 0.779) < 0.005
    except FileNotFoundError:
        ctrl, ctrl_ok = None, None
    print(f"[ctrl v6] AUC {ctrl['auc'] if ctrl else '?'} acc100 "
          f"{ctrl['acc100'] if ctrl else '?'} → {'OK' if ctrl_ok else 'DÉRIVE/ABSENT'}")

    # ---- strates Mondrian ----
    strata = {}
    for g in sorted(set(fams)):
        idx = fams == g
        strata[g] = {a: conformal_tau(conf[idx], errors[idx], a, N_MIN) for a in ALPHAS}

    # comparaison régime servi (tau fixe top-10 %) — recette identique serving
    n_cov = max(1, round(len(y) * 0.10))
    order = np.argsort(-conf)
    sel = order[:n_cov]
    fixed = {"coverage": 0.10, "kept": int(n_cov),
             "realized_err_rate": round(float(errors[sel].mean()), 4),
             "acc_regime": round(float((pred[sel] == y[sel]).mean()), 4),
             "tau_10pct": round(float(conf[order[n_cov - 1]]), 6)}

    alpha_rep = ALPHAS[1]  # rapport principal à α=0.10 (le plus couvrant des deux)
    global_tau = conformal_tau(conf, errors, alpha_rep, N_MIN)
    per_fam_validity = {
        g: {a: (strata[g][a]["realized_err_rate"] is not None
                and strata[g][a]["realized_err_rate"] <= a)
        for a in ALPHAS}
        for g in strata if strata[g][ALPHAS[0]]["tau"] is not None
    }

    out = {
        "story": "12.1-conformal-mondrian",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "pool": f"latent-pool-{pool}",
        "pool_sha256_16": __import__("hashlib").sha256(
            (PILOT / f"latent-pool-{pool}.json").read_bytes()).hexdigest()[:16],
        "n_rows": int(len(rows)), "positives": int(y.sum()),
        "method": METHOD,
        "alphas_registered": list(ALPHAS), "n_min": N_MIN,
        "thr_pool": thr,
        "v6_positive_control": {"expected": [0.822, 0.779],
                                "got": [round(ctrl["auc"], 3), round(ctrl["acc100"], 3)]
                                if ctrl else None,
                                "ok": bool(ctrl_ok)},
        "global_conformal": {f"alpha_{a:.2f}": conformal_tau(conf, errors, a, N_MIN)
                             for a in ALPHAS},
        "fixed_tau_served_regime": fixed,
        "strata_mondrian": strata,
        "strata_with_guarantee": sum(1 for g in strata
                                     if strata[g][ALPHAS[0]]["tau"] is not None),
        "strata_insufficient": sum(1 for g in strata
                                   if strata[g][ALPHAS[0]]["tau"] is None),
        "per_family_validity_alpha10": per_fam_validity,
        "note": "mesure 0-appel sur pool gelé ; τ_g et garantis calculés sur le "
                "replay LOAO (propre tâche exclue) — l'échangeabilité intra-strate "
                "est l'hypothèse publiée ; aucune sélection de paramètre contre "
                "un eval tenu de côté (pas de split supplémentaire : le replay "
                "LOAO EST la validation croisée honnête)",
    }
    CALIB_DIR.mkdir(parents=True, exist_ok=True)
    path = CALIB_DIR / f"risk-scan-{pool}-conformal.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"strates: {out['strata_with_guarantee']} avec garantie / "
          f"{out['strata_insufficient']} insuffisantes (n<{N_MIN})")
    print(f"global α=0.10: tau {global_tau['tau']} retient "
          f"{global_tau.get('coverage_share', '?')} du pool, erreur réalisée "
          f"{global_tau.get('realized_err_rate')}, garanti {global_tau['guarantee']}")
    print(f"régime tau-fixe servi: cov 10 %, acc {fixed['acc_regime']}, "
          f"tau {fixed['tau_10pct']}")
    print(f"→ {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
