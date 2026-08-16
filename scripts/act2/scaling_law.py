#!/usr/bin/env python3
"""Story 12.3 — loi d'échelle couverture↔densité (0 appel, pools gelés v6→v10).

Métrique pré-déclarée AVANT le fit (pas de sélection post-hoc) :
  cov@acc≥0.95 = k*/n, k* = plus grand préfixe (trié par conf décroissante,
  thr médiane gelée) dont l'accuracy reste ≥ 0.95 ; bande par variantes
  acc ≥ 0.97 (k_lo) et acc ≥ 0.93 (k_hi).
Densité = médiane de lignes par famille (préfixe repo).
Forme de fit pré-déclarée : cov(d) = a·(1 − exp(−b·d)) (saturation),
moindres carrés grille déterministe sur 5 points.
L'hypothèse de travail « 10–15 lignes/famille » est remplacée (ou confirmée)
par l'échelle de saturation 1/b fittée.

LIMITES D'EXTRAPOLATION (publiées dans l'artefact) : 5 points, les versions
diffèrent en taille ET en composition (les lignes ajoutées ne sont pas un
échantillon aléatoire) ; densité et n total croissent ensemble ; la courbe est
une TRAJECTOIRE historique, pas une expérience contrôlée — aucune lecture
causale au-delà des points observés, extrapolation au-delà de la plage mesurée
signalée comme non supportée.

Sortie : governance/act2/arm-artifacts/scaling-law-v6-v10.json
Run: uv run python scripts/act2/scaling_law.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
OUT = ROOT / "governance" / "act2" / "arm-artifacts" / "scaling-law-v6-v10.json"
POOL_VERSIONS = ("v6", "v7", "v8", "v9", "v10")

_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)


def cov_at_acc(conf: np.ndarray, correct: np.ndarray, target: float) -> tuple[int, float]:
    order = np.argsort(-conf)
    c = correct[order]
    k_best = 0
    for k in range(1, len(c) + 1):
        if c[:k].mean() >= target:
            k_best = k
        else:
            break  # accuracy de préfixe est monotone décroissante
    return k_best, k_best / len(c)


def point(version: str) -> dict:
    rows = json.loads((PILOT / f"latent-pool-{version}.json").read_text())
    d = np.load(PILOT / f"latent-pool-{version}.npz")
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    fams = {}
    for t in tasks:
        g = t.split(".")[0] if "." in t else t.split(":")[0]
        fams[g] = fams.get(g, 0) + 1
    cd = s11.norm(s11.norm(d["E_state"]) + s11.norm(d["E_diff"]))
    f1 = s11._loao_f1_features(cd, tasks, y)
    thr = float(np.median(f1))
    conf = np.abs(f1 - thr)
    correct = ((f1 > thr).astype(int) == y)
    fam_counts = np.array(sorted(fams.values()))
    k_lo, cov_lo = cov_at_acc(conf, correct, 0.97)
    k, cov = cov_at_acc(conf, correct, 0.95)
    k_hi, cov_hi = cov_at_acc(conf, correct, 0.93)
    return {
        "pool": version, "n_rows": len(rows), "n_pos": int(y.sum()),
        "n_families": len(fams),
        "rows_per_family_median": float(np.median(fam_counts)),
        "rows_per_family_mean": round(float(fam_counts.mean()), 2),
        "rows_per_family_max": int(fam_counts.max()),
        "share_families_ge5": round(float((fam_counts >= 5).mean()), 3),
        "thr": round(thr, 6),
        "cov_at_acc95": round(cov, 4), "k": int(k),
        "ci_band": {"acc97_k": int(k_lo), "cov_lo": round(cov_lo, 4),
                    "acc93_k": int(k_hi), "cov_hi": round(cov_hi, 4)},
        "pool_json_sha256_16": sha256(
            (PILOT / f"latent-pool-{version}.json").read_bytes()).hexdigest()[:16],
    }


def fit_saturation(ds: np.ndarray, covs: np.ndarray) -> dict:
    """Grille déterministe (a,b) minimizing SSE — cov = a(1-exp(-b d)), a∈(0,1]."""
    best = {"sse": float("inf"), "a": None, "b": None}
    for a in np.linspace(0.05, 1.0, 96):
        for b in np.linspace(0.01, 2.0, 200):
            pred = a * (1 - np.exp(-b * ds))
            sse = float(((pred - covs) ** 2).sum())
            if sse < best["sse"]:
                best = {"sse": sse, "a": float(a), "b": float(b)}
    best["saturation_scale_rows_per_family"] = round(1 / best["b"], 1)
    best["rmse"] = round(float(np.sqrt(best["sse"] / len(ds))), 4)
    return best


def _assumption_verdict(pts: list, fit: dict, ds: np.ndarray) -> dict:
    spread = float(ds.max() - ds.min())
    identified = spread >= 1.0  # il faut de la VARIATION de densité pour identifier b
    return {
        "prior": "10–15 lignes/famille (hypothèse de travail)",
        "status": "IDENTIFIÉE" if identified else
                  "NON IDENTIFIABLE sur v6→v10 — ni remplacée ni confirmée : non mesurée",
        "densities_median_observed": [p["rows_per_family_median"] for p in pts],
        "densities_max_observed": [p["rows_per_family_max"] for p in pts],
        "fitted_saturation_scale": fit["saturation_scale_rows_per_family"] if identified else None,
        "raison": "la médiane de lignes/famille est CONSTANTE à 2.0 sur les 5 versions "
                  "(la croissance a ajouté des familles nouvelles, pas de la densité "
                  "dans les familles) ; avec x quasi constant, le paramètre b de "
                  "saturation n'est pas identifiable — le fit est dégénéré et son "
                  "échelle n'est PAS publiée comme une loi" if not identified else
                  "variation de densité suffisante pour le fit",
        "ce_qui_rendrait_la_loi_identifiable": "une fenêtre de croissance PAR "
                  "FAMILLE (renforcement intra-famille à plusieurs niveaux de "
                  "densité, ex. Q3 thin-families poussé à 5/10/15 lignes) — la "
                  "prochaine enveloppe qui vise la loi doit faire varier la densité, "
                  "pas seulement le nombre de familles",
    }


def main() -> int:
    pts = [point(v) for v in POOL_VERSIONS]
    ds = np.array([p["rows_per_family_median"] for p in pts])
    covs = np.array([p["cov_at_acc95"] for p in pts])
    fit = fit_saturation(ds, covs)
    observed = (float(ds.min()), float(ds.max()))
    report = {
        "story": "12.3-scaling-law",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "metric": "cov@acc≥0.95, préfixe par conf décroissante, thr médiane gelée ; "
                  "bande acc≥0.97 / acc≥0.93",
        "fit_model": "cov(d) = a·(1−exp(−b·d)), grille déterministe, pré-déclaré",
        "points": pts,
        "fit": fit,
        "working_assumption_verdict": _assumption_verdict(pts, fit, ds),
        "extrapolation_limits": [
            ("5 points seulement ; le fit à 2 paramètres est sous-déterminé — "
             "RMSE et bande par point publiés, la loi est indicative, pas prédictive"),
            ("les versions diffèrent en taille ET composition (ajouts ciblés, pas "
             "aléatoires) : densité et qualité des lignes croissent ensemble — "
             "confondu non séparable sur ces données"),
            (f"au-delà de la plage observée de densités [{observed[0]:.1f}, "
             f"{observed[1]:.1f}] lignes/famille : EXTRAPOLATION NON SUPPORTÉE "
             "(les fenêtres futures doivent rester dans la plage ou amender la "
             "loi sur nouvelles mesures)"),
        ],
        "next_window_sizing": "les enveloppes de fenêtres citent ce fit pour le "
                              "dimensionnement des quotas (exigence AC 12.3) ; "
                              "citer la plage observée, jamais l'extrapolation",
    }
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    for p in pts:
        print(f"{p['pool']:>4}: n={p['n_rows']:>3} fam={p['n_families']:>2} "
              f"d_médiane={p['rows_per_family_median']:>4.1f} "
              f"cov@95={p['cov_at_acc95']:.3f} [{p['ci_band']['cov_lo']:.3f},"
              f"{p['ci_band']['cov_hi']:.3f}]")
    print(f"fit: a={fit['a']:.3f} b={fit['b']:.3f} rmse={fit['rmse']} → "
          f"échelle saturation ≈ {fit['saturation_scale_rows_per_family']} lignes/famille")
    print(f"→ {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
