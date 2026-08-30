#!/usr/bin/env python3
"""P13 — métriques stratifiées et nulle du MAXIMUM.

Fenêtre : `governance/act2/window-p13-scamper-proposal.md`. ZÉRO appel LLM.

POURQUOI CE MODULE. L'erratum du 2026-08-29 a remplacé l'AUC poolée par l'AUC
INTRA. Le diagnostic du 2026-08-29 va un cran plus loin : sur les paires INTRA
où `persist` SÉPARE DÉJÀ les deux tests (statuts différents au tour a), la
baseline vaut à elle seule 0,91. Un bras peut donc gagner du Δ global sans rien
savoir faire de neuf. La seule strate où la géométrie peut prouver quelque chose
est celle où `persist` est AVEUGLE — les deux tests ont le même statut au tour a,
et la baseline y vaut 0,5000 par construction.

  AUC⊥   : AUC INTRA restreinte aux paires où persist(a) == persist(b).
  AUC⊥⊥  : sous-strate « même test, tours différents » — seul le PATCH change.
           C'est littéralement le cas d'usage `compare_patches`.
           En P12 elle porte 105 des 121 paires de AUC⊥ (86,8 %).

NULLE DU MAXIMUM. On va essayer K variantes sur 121 paires dont les labels sont
connus. La barre n'est donc PAS la nulle d'une variante isolée : c'est le 95e
centile du MAXIMUM des K variantes sous permutation. Sans cette correction, le
meilleur de K tirages passe pour un résultat. Le pair-set est RECALCULÉ à chaque
permutation : la strate aveugle dépend des labels, donc elle bouge avec eux.

Auto-test : .venv/bin/python scripts/act2/p13_metrics.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
AP = ROOT / "data" / "landing" / "act2-pilot"
SRC = {"w46": AP / "transitions" / "v39-transitions.jsonl",
       "p12": AP / "night-harvest" / "py-p12" / "p12-transitions.jsonl",
       "p14": AP / "night-harvest" / "py-p14" / "p14-transitions.jsonl"}
P10 = AP / "night-harvest" / "py-p12" / "p10"

STRATES = ("toutes", "aveugle", "aveugle_meme_test", "informative")


# ------------------------------------------------------------------ chargement
def charge(corpus: str) -> dict:
    """Une ligne = (transition, test déclaré). Même ordre que `p10_fit.py`."""
    trs = [json.loads(l) for l in SRC[corpus].read_text().splitlines() if l.strip()]
    col: dict[str, list] = {k: [] for k in
                            ("inst", "test", "key", "repo", "per", "y", "diff", "turn", "frac")}
    for t in trs:
        dec, rt, rf = t["declared"], set(t["red_to"]), set(t["red_from"])
        frac = len([x for x in dec if x in rf]) / max(1, len(dec))
        for d in dec:
            col["inst"].append(t["instance"]); col["test"].append(d)
            col["key"].append(t["key"]); col["repo"].append(t.get("repo", "?"))
            col["per"].append(1 if d in rf else 0); col["y"].append(1 if d in rt else 0)
            col["diff"].append(t["diff_to"]); col["turn"].append(float(t["turn_to"]))
            col["frac"].append(frac)
    out = {k: np.array(v) for k, v in col.items() if k != "diff"}
    out["diff"] = col["diff"]           # liste de str, pas un tableau numpy
    out["corpus"] = corpus
    return out


# ------------------------------------------------------------------ paires
def paires(y, inst, per, test, key, strate: str = "aveugle") -> np.ndarray:
    """Indices (positif, négatif) d'une MÊME instance, filtrés par strate.

    `y` est passé en argument et non lu d'un état global : sous permutation, la
    strate aveugle change de composition et doit être reconstruite.
    """
    if strate not in STRATES:
        raise ValueError(f"strate inconnue : {strate}")
    out = []
    for i in set(inst.tolist()):
        idx = np.where(inst == i)[0]
        pos = idx[y[idx] == 1]; neg = idx[y[idx] == 0]
        for a in pos:
            for b in neg:
                if strate == "aveugle" and per[a] != per[b]:
                    continue
                if strate == "informative" and per[a] == per[b]:
                    continue
                if strate == "aveugle_meme_test" and not (
                        per[a] == per[b] and test[a] == test[b] and key[a] != key[b]):
                    continue
                out.append((a, b))
    return np.array(out, dtype=np.int64).reshape(-1, 2)


def auc_paires(s, pr: np.ndarray) -> tuple[float, int]:
    """AUC sur une liste EXPLICITE de paires. Les ex aequo comptent 0,5."""
    if not len(pr):
        return float("nan"), 0
    d = np.asarray(s)[pr[:, 0]] - np.asarray(s)[pr[:, 1]]
    return float(((d > 0).sum() + 0.5 * (d == 0).sum()) / len(d)), int(len(d))


def toutes_strates(s, D: dict, y=None) -> dict:
    """AUC des quatre strates d'un coup, pour un vecteur de scores."""
    y = D["y"] if y is None else y
    r = {}
    for st in STRATES:
        pr = paires(y, D["inst"], D["per"], D["test"], D["key"], st)
        a, n = auc_paires(s, pr)
        r[st] = {"auc": None if np.isnan(a) else round(a, 4), "n": n}
    return r


# ------------------------------------------------------------------ permutation
def permute_intra(y, inst, rng) -> np.ndarray:
    """Permute les labels DANS chaque instance : le taux de positifs de
    l'instance est conservé, seul l'appariement ligne <-> label est détruit."""
    yy = y.copy()
    for i in sorted(set(inst.tolist())):
        idx = np.where(inst == i)[0]
        yy[idx] = y[idx][rng.permutation(len(idx))]
    return yy


# ------------------------------------------------------------------ bootstrap
def bootstrap_ci(s, D, strate="aveugle", B=2000, graine=17) -> tuple[float, float]:
    """IC95 par ré-échantillonnage des INSTANCES — jamais des paires : deux
    paires d'une même instance ne sont pas indépendantes."""
    rng = np.random.default_rng(graine)
    insts = np.array(sorted(set(D["inst"].tolist())))
    par_inst = {i: paires(D["y"], D["inst"], D["per"], D["test"], D["key"], strate)
                for i in insts}
    par_inst = {i: p[D["inst"][p[:, 0]] == i] if len(p) else p for i, p in par_inst.items()}
    vals = []
    for _ in range(B):
        tir = rng.choice(insts, size=len(insts), replace=True)
        pr = np.concatenate([par_inst[i] for i in tir if len(par_inst[i])]) \
            if any(len(par_inst[i]) for i in tir) else np.zeros((0, 2), dtype=np.int64)
        a, n = auc_paires(s, pr)
        if n:
            vals.append(a)
    if not vals:
        return float("nan"), float("nan")
    return round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)


# ------------------------------------------------------------------ auto-test
def _autotest() -> int:
    ok = True
    for corpus, att in (("w46", {"aveugle": 54, "aveugle_meme_test": 20, "toutes": 135}),
                        ("p12", {"aveugle": 121, "aveugle_meme_test": 105, "toutes": 408})):
        D = charge(corpus)
        print(f"\n=== {corpus} : {len(D['y'])} lignes · {int(D['y'].sum())} positifs "
              f"· {len(set(D['inst'].tolist()))} instances")
        for st, n_att in att.items():
            pr = paires(D["y"], D["inst"], D["per"], D["test"], D["key"], st)
            marque = "OK " if len(pr) == n_att else "ÉCART"
            ok &= len(pr) == n_att
            print(f"  {st:20s} {len(pr):4d} paires  (attendu {n_att})  {marque}")
        # `persist` DOIT valoir exactement 0,5000 sur la strate aveugle : c'est
        # la définition même de la strate, et donc un contrôle de la construction.
        pr = paires(D["y"], D["inst"], D["per"], D["test"], D["key"], "aveugle")
        a, _ = auc_paires(D["per"].astype(float), pr)
        marque = "OK " if abs(a - 0.5) < 1e-12 else "ÉCART"
        ok &= abs(a - 0.5) < 1e-12
        print(f"  contrôle : AUC⊥ de `persist` = {a:.4f} (doit être 0.5000)  {marque}")
        # contrôle positif sur les p_raw déjà en cache
        for bras in ("complet", "Ed", "Et"):
            f = P10 / f"p_raw-{corpus}-{bras}.npy"
            if not f.is_file():
                continue
            s = np.load(f)
            r = toutes_strates(s, D)
            print(f"  {bras:8s} ⊥ {r['aveugle']['auc']}  ⊥⊥ {r['aveugle_meme_test']['auc']}"
                  f"  informative {r['informative']['auc']}  toutes {r['toutes']['auc']}")
    print("\nAUTO-TEST :", "OK" if ok else "ÉCHEC")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_autotest())
