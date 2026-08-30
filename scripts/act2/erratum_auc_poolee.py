#!/usr/bin/env python3
"""Erratum métrologique — l'AUC POOLÉE en LOO ne mesure pas ce qu'elle annonce.

Reproduction : .venv/bin/python scripts/act2/erratum_auc_poolee.py
Zéro appel LLM. Écrit UNIQUEMENT l'artefact de mesure, aucun artefact scellé.

DÉFAUT. L'AUC poolée compare des points notés par des MODÈLES DIFFÉRENTS — un
par pli. L'intercept de chacun dépend du taux de positifs de son jeu
d'entraînement, qui change à chaque pli retiré. Ce décalage de niveau contamine
les paires INTER-instances, qui pèsent plus de 99 % des paires de l'AUC poolée.

MESURE DU DÉFAUT. On permute les labels DANS CHAQUE INSTANCE : le taux de
positifs de chaque instance est préservé, seul l'appariement interne est
détruit. Toute AUC restante ne peut plus venir que de la capacité à classer les
INSTANCES entre elles. C'est le plancher de la métrique — sa vraie valeur sous
H0, à comparer au 0,50 supposé.

MÉTRIQUE DE REMPLACEMENT. L'AUC INTRA ne retient que les paires
(positif, négatif) d'une MÊME instance : les deux points y sont notés par le
même modèle, le décalage de pli s'annule exactement. C'est aussi la seule qui
corresponde au produit — `predict_transition` rend une probabilité par test pour
les tests déclarés d'UNE instance.

Les deux structures de plis sont mesurées, car le chiffre servi (v41,
T1_auc.modele = 0.9931) a été produit en LOO par TRAJECTOIRE, pas par instance.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
AP = ROOT / "data" / "landing" / "act2-pilot"
SRC = {"w46": AP / "transitions" / "v39-transitions.jsonl",
       "p12": AP / "night-harvest" / "py-p12" / "p12-transitions.jsonl"}
P10 = AP / "night-harvest" / "py-p12" / "p10"
OUT = AP / "night-harvest" / "py-p12" / "erratum-auc-poolee-2026-08-29.json"
N_PERM = 20
C = 50.0
_W: dict = {}


def charge(corpus):
    trs = [json.loads(l) for l in SRC[corpus].read_text().splitlines() if l.strip()]
    inst, traj, y = [], [], []
    for t in trs:
        rt = set(t["red_to"])
        # clé de trajectoire de la convention v39 : (instance, modèle)
        k = f"{t['instance']}|{t['model']}"
        for d in t["declared"]:
            inst.append(t["instance"]); traj.append(k)
            y.append(1 if d in rt else 0)
    return np.array(inst), np.array(traj), np.asarray(y)


def auc_gen(s, y, inst, mode):
    pos = np.where(y == 1)[0]; neg = np.where(y == 0)[0]
    n = 0; g = 0.0
    for i in pos:
        m = neg[inst[neg] == inst[i]] if mode == "intra" else neg
        if not len(m):
            continue
        d = s[i] - s[m]
        g += float((d > 0).sum() + 0.5 * (d == 0).sum()); n += len(m)
    return (g / n if n else float("nan")), n


def _init(xp, gp, ip):
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[v] = "1"
    _W["X"] = np.load(xp, mmap_mode="r")
    _W["g"] = np.load(gp, allow_pickle=True)
    _W["inst"] = np.load(ip, allow_pickle=True)


def _task(arg):
    graine, y_ref = arg
    from sklearn.linear_model import LogisticRegression
    X, g, inst = np.asarray(_W["X"]), _W["g"], _W["inst"]
    folds = sorted(set(g.tolist()))
    rng = np.random.default_rng(graine)
    yy = y_ref.copy()
    # permutation DANS L'INSTANCE : le taux de positifs de chaque instance est
    # conservé ; seul l'appariement test <-> label est détruit.
    for gg in sorted(set(inst.tolist())):
        idx = np.where(inst == gg)[0]
        yy[idx] = y_ref[idx][rng.permutation(len(idx))]
    p = np.zeros(len(yy))
    for gg in folds:
        te = g == gg; tr = ~te
        if yy[tr].sum() == 0 or yy[tr].sum() == tr.sum():
            p[te] = float(yy[tr].mean()); continue
        clf = LogisticRegression(penalty="l2", C=C, solver="lbfgs",
                                 max_iter=5000).fit(X[tr], yy[tr])
        p[te] = clf.predict_proba(X[te])[:, 1]
    return (auc_gen(p, yy, inst, "intra")[0], auc_gen(p, yy, inst, None)[0])


def loo_obs(X, y, g):
    from sklearn.linear_model import LogisticRegression
    p = np.zeros(len(y))
    for gg in sorted(set(g.tolist())):
        te = g == gg; tr = ~te
        if y[tr].sum() == 0 or y[tr].sum() == tr.sum():
            p[te] = float(y[tr].mean()); continue
        clf = LogisticRegression(penalty="l2", C=C, solver="lbfgs",
                                 max_iter=5000).fit(X[tr], y[tr])
        p[te] = clf.predict_proba(X[te])[:, 1]
    return p


def main() -> int:
    rap = {"at": datetime.now(UTC).isoformat(), "n_permutations": N_PERM,
           "permutation": "intra-instance (taux de positifs par instance conservé)",
           "corpus": {}}
    for corpus in ("w46", "p12"):
        inst, traj, y = charge(corpus)
        X = np.load(P10 / f"_X-{corpus}.npy", mmap_mode="r")
        if X.shape[0] != len(y):
            print(f"{corpus} : X {X.shape} != {len(y)} paires — sauté")
            continue
        rap["corpus"][corpus] = {"n_paires": int(len(y)), "n_positifs": int(y.sum()),
                                 "n_instances": len(set(inst.tolist())),
                                 "n_trajectoires": len(set(traj.tolist())), "plis": {}}
        for nom, g in (("instance", inst), ("trajectoire", traj)):
            gp = P10 / f"_grp-{corpus}-{nom}.npy"
            ip = P10 / f"_inst-{corpus}.npy"
            np.save(gp, g, allow_pickle=True)
            np.save(ip, inst, allow_pickle=True)
            obs = loo_obs(np.asarray(X), y, g)
            o_in = auc_gen(obs, y, inst, "intra")
            o_po = auc_gen(obs, y, inst, None)
            res = []
            with cf.ProcessPoolExecutor(max_workers=6, initializer=_init,
                                        initargs=(str(P10 / f"_X-{corpus}.npy"),
                                                  str(gp), str(ip))) as ex:
                for a in ex.map(_task, [(2000 + k, y) for k in range(N_PERM)]):
                    res.append(a)
            A = np.array([r for r in res if np.isfinite(r[0])])
            bloc = {"n_plis": len(set(g.tolist()))}
            for j, (mk, o) in enumerate((("intra", o_in), ("poolee", o_po))):
                col = A[:, j]
                bloc[mk] = {"observee": round(float(o[0]), 4), "n_paires": int(o[1]),
                            "nulle_moyenne": round(float(col.mean()), 4),
                            "nulle_ecart_type": round(float(col.std(ddof=1)), 4),
                            "nulle_max": round(float(col.max()), 4),
                            "biais": round(float(col.mean() - 0.5), 4),
                            "ecarts_types_au_dessus_de_la_nulle":
                                round(float((o[0] - col.mean()) / col.std(ddof=1)), 2)}
            rap["corpus"][corpus]["plis"][nom] = bloc
            print(f"{corpus} / LOO {nom} ({bloc['n_plis']} plis)", flush=True)
            for mk in ("intra", "poolee"):
                b = bloc[mk]
                print(f"  {mk:7s} observée {b['observee']:.4f} · nulle {b['nulle_moyenne']:.4f} "
                      f"(biais {b['biais']:+.4f}, sd {b['nulle_ecart_type']:.4f}, "
                      f"max {b['nulle_max']:.4f}) · {b['ecarts_types_au_dessus_de_la_nulle']:+.2f} sd",
                      flush=True)
    OUT.write_text(json.dumps(rap, ensure_ascii=False, indent=1))
    print(f"\nécrit : {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
