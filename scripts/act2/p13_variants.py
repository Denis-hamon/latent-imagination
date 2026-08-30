#!/usr/bin/env python3
"""P13 — banc de variantes. Fenêtre `governance/act2/window-p13-scamper-proposal.md`.

ZÉRO appel LLM. Vagues 1 et 3 : zéro ré-encodage, tout part du `_X-<corpus>.npy`
déjà en cache (blocs `[Ed(768) | Et(768) | cos(1) | persist frac turn(3)]`).

RÈGLE DE LA FENÊTRE. `C` n'est PAS balayé et lu de l'extérieur — ce serait K = 9
variantes de plus et un choix fait sur les labels d'évaluation. Il est choisi
DANS LE PLI par validation croisée interne groupée par instance, au critère de
log-vraisemblance (sans seuil, insensible au déséquilibre). Idem pour la
dimension de la PCA de `V4`.

Usage :
  .venv/bin/python scripts/act2/p13_variants.py --corpus p12 --variantes V1,V2
  .venv/bin/python scripts/act2/p13_variants.py --corpus w46 --variantes V1  # contrôle positif
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

ROOT = Path(__file__).resolve().parents[2]
AP = ROOT / "data" / "landing" / "act2-pilot"
P10 = AP / "night-harvest" / "py-p12" / "p10"
OUT = AP / "night-harvest" / "py-p12" / "p13"

GRILLE_C = (0.003, 0.03, 0.3, 3.0, 50.0)
GRILLE_PCA = (16, 32, 64)
N_INNER = 3


# ------------------------------------------------------------------ socle
def blocs(corpus: str) -> dict:
    """Découpe `_X-<corpus>.npy` en ses blocs d'origine. Ordre figé par
    `p10_fit.py` : concatenate([D, T, cos, scal])."""
    X = np.load(P10 / f"_X-{corpus}.npy")
    assert X.shape[1] == 1540, X.shape
    return {"_corpus": corpus, "Ed": X[:, :768], "Et": X[:, 768:1536], "cos": X[:, 1536:1537],
            "scal": X[:, 1537:1540], "persist": X[:, 1537:1538], "X": X}


def _plis_internes(g, tr, n=N_INNER):
    """Plis internes GROUPÉS PAR INSTANCE, découpés dans le jeu d'entraînement
    seulement. Un pli interne qui casserait le groupement laisserait deux tours
    d'une même instance des deux côtés."""
    gi = np.array(sorted(set(g[tr].tolist())))
    return [np.isin(g, gi[k::n].tolist()) & tr for k in range(n)]


def _logvrais(pv, yv) -> float:
    eps = 1e-9
    return float(np.sum(yv * np.log(pv + eps) + (1 - yv) * np.log(1 - pv + eps)) / len(yv))


def _fit(C, Xa, ya, Xb, it=5000):
    from sklearn.linear_model import LogisticRegression
    return LogisticRegression(C=C, solver="lbfgs", max_iter=it).fit(Xa, ya).predict_proba(Xb)[:, 1]


def loo_C_dans_le_pli(X, y, g, folds, grille=GRILLE_C) -> np.ndarray:
    """LOO par instance ; `C` choisi dans le pli. Aucune information du pli
    d'évaluation ne participe au choix de `C`."""
    p = np.zeros(len(y))
    for gg in folds:
        te = g == gg; tr = ~te
        if y[tr].sum() == 0 or y[tr].sum() == tr.sum():
            p[te] = float(y[tr].mean()) if tr.sum() else 0.5
            continue
        best, bs = grille[0], -np.inf
        for C in grille:
            s, n = 0.0, 0
            for va in _plis_internes(g, tr):
                en = tr & ~va
                if y[en].sum() in (0, en.sum()) or not va.sum():
                    continue
                s += _logvrais(_fit(C, X[en], y[en], X[va], 2000), y[va]); n += 1
            if n and s / n > bs:
                bs, best = s / n, C
        p[te] = _fit(best, X[tr], y[tr], X[te])
    return p


# ------------------------------------------------------------------ variantes
def _V_statique(cles):
    """Fabrique une variante « concaténation statique + C dans le pli »."""
    def f(B, y, g, folds):
        X = np.concatenate([B[k] for k in cles], axis=1)
        return loo_C_dans_le_pli(X, y, g, folds)
    return f


def V4_pca(B, y, g, folds):
    """PCA ajustée DANS LE PLI sur Ed et Et séparément ; dimension choisie dans
    le pli. Ajuster la PCA hors du pli ferait voir au modèle la géométrie des
    points qu'il doit noter."""
    from sklearn.decomposition import PCA
    p = np.zeros(len(y))
    for gg in folds:
        te = g == gg; tr = ~te
        if y[tr].sum() == 0 or y[tr].sum() == tr.sum():
            p[te] = float(y[tr].mean()) if tr.sum() else 0.5
            continue
        best, bs = (GRILLE_PCA[0], GRILLE_C[0]), -np.inf
        proj = {}
        for k in GRILLE_PCA:
            pd_ = PCA(n_components=k, random_state=0).fit(B["Ed"][tr])
            pt_ = PCA(n_components=k, random_state=0).fit(B["Et"][tr])
            proj[k] = np.concatenate([pd_.transform(B["Ed"]), pt_.transform(B["Et"]),
                                      B["cos"], B["scal"]], axis=1)
            for C in GRILLE_C:
                s, n = 0.0, 0
                for va in _plis_internes(g, tr):
                    en = tr & ~va
                    if y[en].sum() in (0, en.sum()) or not va.sum():
                        continue
                    s += _logvrais(_fit(C, proj[k][en], y[en], proj[k][va], 2000), y[va]); n += 1
                if n and s / n > bs:
                    bs, best = s / n, (k, C)
        Xb = proj[best[0]]
        p[te] = _fit(best[1], Xb[tr], y[tr], Xb[te])
    return p


def V5_fusion_tardive(B, y, g, folds):
    """Deux scoreurs séparés (Ed, Et), puis un 2e étage à 6 d.

    Le 2e étage est ajusté sur des scores HORS-PLI du 1er étage, produits par une
    validation croisée interne groupée : l'ajuster sur des scores en re-substitution
    lui apprendrait la sur-confiance du 1er étage plutôt que la façon de le corriger.
    """
    Xd = np.concatenate([B["Ed"], B["cos"], B["scal"]], axis=1)
    Xt = np.concatenate([B["Et"], B["cos"], B["scal"]], axis=1)
    p = np.zeros(len(y))
    for gg in folds:
        te = g == gg; tr = ~te
        if y[tr].sum() == 0 or y[tr].sum() == tr.sum():
            p[te] = float(y[tr].mean()) if tr.sum() else 0.5
            continue
        z = {}
        for nom, Xr in (("d", Xd), ("t", Xt)):
            zz = np.zeros(len(y))
            for va in _plis_internes(g, tr, 5):
                en = tr & ~va
                if y[en].sum() in (0, en.sum()) or not va.sum():
                    zz[va] = float(y[en].mean()) if en.sum() else 0.5
                    continue
                zz[va] = _fit(1.0, Xr[en], y[en], Xr[va], 2000)
            zz[te] = _fit(1.0, Xr[tr], y[tr], Xr[te])   # 1er étage vu tout l'entraînement
            z[nom] = zz
        M = np.concatenate([z["d"][:, None], z["t"][:, None], B["cos"], B["scal"]], axis=1)
        p[te] = _fit(1.0, M[tr], y[tr], M[te])
    return p


VARIANTES = {
    "V1": ("complet 1540 d, C dans le pli", _V_statique(["Ed", "Et", "cos", "scal"])),
    "V2": ("Ed + scalaires, C dans le pli", _V_statique(["Ed", "cos", "scal"])),
    "V3": ("Et + scalaires, C dans le pli", _V_statique(["Et", "cos", "scal"])),
    "V4": ("PCA(Ed) + PCA(Et) dans le pli", V4_pca),
    "V5": ("fusion tardive 6 d, LOO imbriqué", V5_fusion_tardive),
    "V6": ("V1 sans frac ni turn", _V_statique(["Ed", "Et", "cos", "persist"])),
}


# ------------------------------------------------- vague 2 : représentations
def _E(corpus, nom):
    p = OUT / f"_E-{corpus}-{nom}.npy"
    if not p.is_file():
        raise SystemExit(f"manquant : {p} — lancer d'abord "
                         f"`.venv/bin/python scripts/act2/p13_features.py --corpus {corpus}`")
    return np.load(p)


def _cos(A, B_):
    return np.einsum("ij,ij->i", A, B_)[:, None]


def _V_repr(quoi):
    """V7 à V10 : mêmes blocs, représentations substituées. `C` dans le pli."""
    def f(B, y, g, folds, corpus=None):
        c = corpus or B["_corpus"]
        if quoi == "hunks":                       # V7 : la DISTRIBUTION des cos test<->hunk
            X = np.concatenate([B["cos"], _E(c, "hunkagg"), B["scal"]], axis=1)
        else:
            Ed = _E(c, "ast") if "ast" in quoi else B["Ed"]
            Et = _E(c, "corps") if "corps" in quoi else B["Et"]
            X = np.concatenate([Ed, Et, _cos(Ed, Et), B["scal"]], axis=1)
        return loo_C_dans_le_pli(X, y, g, folds)
    return f


# ------------------------------------------------- vague 3 : objectif, population
def _conditionnel(B, y, g, folds, blocs_utilises):
    """Coeur commun a V11 et V14. Extrait tel quel du corps de V11 : seule la
    liste des blocs devient un parametre, la valeur par defaut de V11 reproduit
    exactement ses chiffres publies."""
    """Logistique CONDITIONNELLE sur les différences intra-instance (Bradley-Terry).

    On mesure un classement DANS l'instance et on entraînait un pointwise poolé :
    l'intercept d'instance, que la métrique annule, était appris comme du signal.
    Ici l'unité d'entraînement est la paire (positif, négatif) d'une même instance,
    la cible est le signe, et le modèle est sans intercept — l'effet d'instance
    disparaît par construction, exactement comme dans l'AUC⊥.
    """
    from sklearn.linear_model import LogisticRegression
    X = np.concatenate([B[k] for k in blocs_utilises], axis=1)
    p = np.zeros(len(y))
    for gg in folds:
        te = g == gg; tr = ~te
        D_ = []
        for i in set(g[tr].tolist()):
            idx = np.where(g == i)[0]
            pos = idx[y[idx] == 1]; neg = idx[y[idx] == 0]
            for a_ in pos:
                for b_ in neg:
                    D_.append(X[a_] - X[b_])
        if len(D_) < 4:
            p[te] = float(y[tr].mean()) if tr.sum() else 0.5
            continue
        Dm = np.asarray(D_)
        # jeu symétrisé : (+d -> 1) et (-d -> 0), sans intercept
        Xp = np.vstack([Dm, -Dm]); yp = np.r_[np.ones(len(Dm)), np.zeros(len(Dm))]
        # C=1.0 fixe a priori : la selection dans le pli a ete mesuree nuisible
        # (vague 1), et un C choisi apres coup serait un choix sur le resultat.
        clf = LogisticRegression(C=1.0, fit_intercept=False, solver="lbfgs",
                                 max_iter=5000).fit(Xp, yp)
        p[te] = X[te] @ clf.coef_.ravel()      # score, pas une probabilité : l'AUC ne lit qu'un ordre
    return p


def V11_conditionnel(B, y, g, folds):
    """Logistique CONDITIONNELLE, representation COMPLETE — inchangee."""
    return _conditionnel(B, y, g, folds, ["Ed", "Et", "cos", "scal"])


def V14_conditionnel_sans_scalaires(B, y, g, folds):
    """P15 — les DEUX leviers mesures, combines pour la premiere fois.

    Levier 1, l'objectif : conditionnel intra-instance au lieu de ponctuel poole
    (V11, 0,9444 contre 0,8333 pour le modele servi sur w46).

    Levier 2, la representation : retrait des scalaires ponctuels. Mesure quatre
    fois, sur deux corpus — `Ed` seul bat le modele complet (w46 0,8704 > 0,8333 ;
    P12 0,5372 > 0,4793) et V6 sans frac ni turn bat V1 (+0,111 w46, +0,091 P12).

    Le mecanisme n'est pas infere : sur la strate aveugle `persist` est CONSTANT
    dans la paire, donc il s'annule dans la difference X[a] - X[b] et ne peut rien
    classer, tout en consommant de la capacite au fit ; `frac` et `turn` y varient
    sans porter d'information sur le sort du test.

    Gelee dans window-p15-objectif-paires-proposal.md AVANT que P14 rende.
    """
    return _conditionnel(B, y, g, folds, ["Ed", "Et", "cos"])


def V12_stratifie(B, y, g, folds):
    """Un modèle par strate de `persist` : 3,9 % de positifs d'un côté, 55,4 %
    de l'autre. Un modèle unique moyenne deux régimes incomparables."""
    X = np.concatenate([B["Ed"], B["Et"], B["cos"], B["scal"]], axis=1)
    per = B["persist"].ravel()
    p = np.zeros(len(y))
    for v in (0.0, 1.0):
        m = per == v
        if not m.sum():
            continue
        sub = loo_C_dans_le_pli(X[m], y[m], g[m], sorted(set(g[m].tolist())))
        p[m] = sub
    return p


def V13_conjoint(B, y, g, folds):
    """Fit conjoint w46 + P12 avec indicatrice de corpus. DIVULGATION DW-37 :
    deux populations, deux langages, deux solveurs. w46 est TOUJOURS en
    entraînement, l'évaluation ne porte que sur P12."""
    Xp = np.concatenate([B["Ed"], B["Et"], B["cos"], B["scal"]], axis=1)
    Xw = np.load(P10 / "_X-w46.npy")
    yw = np.load(P10 / "_y-w46.npy")
    Xp = np.hstack([Xp, np.ones((len(Xp), 1))])
    Xw = np.hstack([Xw, np.zeros((len(Xw), 1))])
    p = np.zeros(len(y))
    for gg in folds:
        te = g == gg; tr = ~te
        Xa = np.vstack([Xp[tr], Xw]); ya = np.r_[y[tr], yw]
        # C=50 : la valeur de la convention v39/v41, fixee AVANT le premier run
        # de V13 pour ne pas etre un choix fait sur le resultat. Le finding de
        # la vague 1 (choisir C dans le pli degrade l'AUC-PERP) interdit ici la
        # selection interne.
        p[te] = _fit(50.0, Xa, ya, Xp[te])
    return p


VARIANTES.update({
    "V7": ("cos test<->hunk (distribution)", _V_repr("hunks")),
    "V8": ("Et -> corps du test (test_patch)", _V_repr("corps")),
    "V9": ("Ed -> diff AST-normalisé", _V_repr("ast")),
    "V10": ("AST + corps du test", _V_repr("ast+corps")),
    "V11": ("logistique conditionnelle (intra)", V11_conditionnel),
    "V12": ("fit stratifié par persist", V12_stratifie),
    "V13": ("conjoint w46+P12 (DW-37)", V13_conjoint),
})
# Hors des treize gelees par P13 : hypothese UNIQUE de P15, jugee sur P14 seul.
# Separee volontairement — la barre de P13 est la nulle du MAXIMUM de treize, et
# V14 ne doit jamais y etre compte en douce.
VARIANTES_P15 = {
    "V14": ("P15 — conditionnel SANS scalaires ponctuels", V14_conditionnel_sans_scalaires),
}
VARIANTES.update(VARIANTES_P15)


# ------------------------------------------------------------------ exécution
def joue(vid: str, corpus: str, B, y, g, folds, D, M) -> dict:
    import time
    lib, fn = VARIANTES[vid]
    t0 = time.time()
    p = fn(B, y, g, folds)
    dt = time.time() - t0
    np.save(OUT / f"p_raw-{corpus}-{vid}.npy", p)
    r = M.toutes_strates(p, D)
    lo, hi = M.bootstrap_ci(p, D, "aveugle")
    res = {"variante": vid, "libelle": lib, "corpus": corpus,
           "secondes": round(dt, 1), "strates": r, "ic95_aveugle": [lo, hi]}
    print(f"  {vid:4s} {lib:38s} ⊥ {r['aveugle']['auc']}  IC95 [{lo}, {hi}]"
          f"  ⊥⊥ {r['aveugle_meme_test']['auc']}  informative {r['informative']['auc']}"
          f"  toutes {r['toutes']['auc']}  ({dt:.0f} s)", flush=True)
    return res


def main() -> int:
    import sys
    sys.path.insert(0, str(ROOT / "scripts" / "act2"))
    import p13_metrics as M

    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=("w46", "p12"), required=True)
    ap.add_argument("--variantes", default=",".join(VARIANTES))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    D = M.charge(a.corpus)
    B = blocs(a.corpus)
    y = np.load(P10 / f"_y-{a.corpus}.npy")
    g = np.load(P10 / f"_g-{a.corpus}.npy", allow_pickle=True)
    assert len(y) == B["X"].shape[0] == len(D["y"]) and (y == D["y"]).all(), \
        "desynchronisation entre le cache p10 et le chargement p13"
    folds = sorted(set(g.tolist()))
    print(f"corpus {a.corpus} : {len(y)} lignes · {int(y.sum())} positifs · "
          f"{len(folds)} plis · strate aveugle "
          f"{len(M.paires(y, D['inst'], D['per'], D['test'], D['key'], 'aveugle'))} paires",
          flush=True)

    rap = {"at": datetime.now(UTC).isoformat(), "corpus": a.corpus,
           "fenetre": "governance/act2/window-p13-scamper-proposal.md",
           "grille_C": list(GRILLE_C), "grille_pca": list(GRILLE_PCA),
           "n_plis_internes": N_INNER, "variantes": {}}
    for vid in [v.strip() for v in a.variantes.split(",") if v.strip()]:
        rap["variantes"][vid] = joue(vid, a.corpus, B, y, g, folds, D, M)

    f = OUT / f"p13-{a.corpus}-{'-'.join(rap['variantes'])}.json"
    f.write_text(json.dumps(rap, ensure_ascii=False, indent=1))
    print(f"\nécrit : {f}\nsha256 : {hashlib.sha256(f.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------- LORO (P14)
# Blocs des variantes couvertes. Le LORO exige un fit UNIQUE hors-depot, pas le
# LOO imbrique des variantes : il n'est donc pas derivable mecaniquement de
# n'importe quelle variante (V4 ajuste une PCA dans le pli, V5 une fusion
# tardive, V12 une stratification). On couvre les deux familles ou la question
# se pose reellement, et on le DIT.
LORO_BLOCS = {
    "V1": (["Ed", "Et", "cos", "scal"], "statique"),
    "V2": (["Ed", "cos", "scal"], "statique"),
    "V3": (["Et", "cos", "scal"], "statique"),
    "V6": (["Ed", "Et", "cos", "persist"], "statique"),
    "V11": (["Ed", "Et", "cos", "scal"], "conditionnel"),
    "V14": (["Ed", "Et", "cos"], "conditionnel"),
}

# Precondition de LISIBILITE, gelee dans window-p14-variance-proposal.md le
# 2026-08-29, AVANT le rejeu. Un depot retire qui n'apporte que 4 instances
# rend une AUC dont l'intervalle avale l'ecart entre 0,50 et le seuil de 0,60 :
# le critere y passe ou echoue par bruit. Mesure sur P12 : tobymao 69 paires /
# 18 instances, python-pillow 26 / 6, iterative 26 / 4.
LORO_MIN_INSTANCES = 10
LORO_MIN_PAIRES = 30


def loro(vid, corpus, B, y, D, M, seuil=0.60):
    """Leave-one-repo-out : fit UNIQUE hors du depot retire, score sur lui,
    AUC lue sur SA strate aveugle.

    Ce n'est pas le LOO imbrique des variantes, et c'est declare — meme
    protocole que `w48b_refit.py`, ou il etait deja descriptif.

    Un depot non lisible est rendu « non evaluable » : ni succes ni echec. Les
    deux seraient des affirmations que la donnee ne porte pas.
    """
    if vid not in LORO_BLOCS:
        return {"couvert": False, "raison": "protocole non derivable pour cette variante"}
    cles, famille = LORO_BLOCS[vid]
    X = np.concatenate([B[k] for k in cles], axis=1)
    inst = D["inst"]
    # Le depot se lit dans le prefixe de l'identifiant SWE-bench (`repo__nom-NNN`).
    # Sur w46 les instances synthetiques n'ont pas cette forme et rendent un
    # pseudo-depot par test — sans effet sur le verdict (elles portent zero paire
    # aveugle), mais a savoir avant de lire la ventilation de w46.
    dep = np.array([str(i).split("__")[0] for i in inst])
    out = {"couvert": True, "famille": famille, "seuil": seuil, "par_depot": {}}

    for r in sorted(set(dep.tolist())):
        te = dep == r
        tr = ~te
        pr = M.paires(y, inst, D["per"], D["test"], D["key"], "aveugle")
        # paires aveugles PORTEES par ce depot
        pr_r = pr[te[pr[:, 0]]] if len(pr) else pr
        n_paires = len(pr_r)
        n_inst = len({str(inst[a]) for a, _ in pr_r}) if n_paires else 0

        if n_inst < LORO_MIN_INSTANCES or n_paires < LORO_MIN_PAIRES:
            out["par_depot"][r] = {"lisible": False, "paires": n_paires,
                                   "instances": n_inst, "auc": None}
            continue
        if y[tr].sum() == 0 or y[tr].sum() == tr.sum():
            out["par_depot"][r] = {"lisible": False, "paires": n_paires,
                                   "instances": n_inst, "auc": None,
                                   "raison": "une seule classe hors depot"}
            continue

        if famille == "statique":
            p = np.zeros(len(y))
            p[te] = _fit(50.0, X[tr], y[tr], X[te])
        else:
            from sklearn.linear_model import LogisticRegression
            Dm = []
            for i in set(inst[tr].tolist()):
                idx = np.where(inst == i)[0]
                pos = idx[y[idx] == 1]; neg = idx[y[idx] == 0]
                for a_ in pos:
                    for b_ in neg:
                        Dm.append(X[a_] - X[b_])
            if len(Dm) < 4:
                out["par_depot"][r] = {"lisible": False, "paires": n_paires,
                                       "instances": n_inst, "auc": None,
                                       "raison": "moins de 4 paires d'entrainement"}
                continue
            Dm = np.asarray(Dm)
            Xp = np.vstack([Dm, -Dm]); yp = np.r_[np.ones(len(Dm)), np.zeros(len(Dm))]
            clf = LogisticRegression(C=1.0, fit_intercept=False, solver="lbfgs",
                                     max_iter=5000).fit(Xp, yp)
            p = np.zeros(len(y))
            p[te] = X[te] @ clf.coef_.ravel()

        a = float((p[pr_r[:, 0]] > p[pr_r[:, 1]]).mean()
                  + 0.5 * (p[pr_r[:, 0]] == p[pr_r[:, 1]]).mean())
        out["par_depot"][r] = {"lisible": True, "paires": n_paires,
                               "instances": n_inst, "auc": round(a, 4)}

    lisibles = [v for v in out["par_depot"].values() if v["lisible"]]
    out["n_lisibles"] = len(lisibles)
    if len(lisibles) < 2:
        # Clause non evaluable : JAMAIS retrogradee en silence vers un echec.
        out["verdict"] = "NON EVALUABLE"
    elif all(v["auc"] >= seuil for v in lisibles):
        out["verdict"] = "SATISFAIT"
    else:
        out["verdict"] = "ECHOUE"
    return out
