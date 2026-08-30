#!/usr/bin/env python3
"""P10 — fit de la recette v39 sur le corpus P12, protocole corrigé.

Fenêtre : `governance/act2/window-p10-fit-proposal.md`. ZÉRO appel LLM.

Protocole pré-enregistré dans `plan-parite-python-jsts-2026-08-27.md` §P10 :
  - AUC mesurée sur `p_raw` — JAMAIS sur la sortie isotonic. L'erratum du
    2026-08-25 (ledger 172) a montré que l'isotonic ajustée sur les mêmes `y`
    que l'évaluation fabrique du gain à partir des labels, d'autant plus que le
    classement brut est mauvais — donc surtout pour la baseline.
  - Isotonic et seuil de Youden ajustés DANS LE PLI : pour le pli `g`, tous
    deux sont ajustés sur les prédictions hors-pli des AUTRES plis, et n'ont
    donc jamais vu les labels des points qu'ils calibrent.
  - LOO PAR INSTANCE (et non par trajectoire) : deux trajectoires d'une même
    instance partagent le ticket, le patch de test et les tests déclarés.
  - Bras : géométrie complète 1540 d ; ablations Ed / Et / scalaires ;
    baseline `persist`.
  - CONTRÔLE POSITIF obligatoire : le même code sur w46 doit rendre
    0,966 ± 0,01. Sans lui, un échec en Python ne prouve rien.
  - CONTRÔLE NÉGATIF obligatoire : labels permutés → AUC ≈ 0,50. Deux
    permutations : GLOBALE (le lien X↔y détruit partout) et DANS L'INSTANCE
    (chaque instance garde son taux de positifs). La seconde vise la réserve du
    verdict P12 — un modèle qui noterait en reconnaissant l'instance plutôt que
    la transition garderait de l'AUC sous permutation globale seule.

Usage :
  .venv/bin/python scripts/act2/p10_fit.py --corpus w46   # contrôle positif
  .venv/bin/python scripts/act2/p10_fit.py --corpus p12   # la mesure
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("LI_ENCODER", "jinaai/jina-embeddings-v2-base-code")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402

AP = ROOT / "data" / "landing" / "act2-pilot"
NH = AP / "night-harvest"
SOURCES = {
    "w46": AP / "transitions" / "v39-transitions.jsonl",
    "p12": NH / "py-p12" / "p12-transitions.jsonl",
    "p14": NH / "py-p14" / "p14-transitions.jsonl",
}
OUT = NH / "py-p12" / "p10"
CACHES = [AP / "w48" / "emb-cache.npz", NH / "py-p3" / "p4" / "emb-cache-p4.npz",
          NH / "py-p3" / "p6" / "emb-cache-p6.npz", OUT / "emb-cache-p10.npz"]
C = 50.0
# 4 workers d'encodage saturaient le swap (660 Mo chacun sur 3 Go) : le debit
# tombait a 8 textes par quart d'heure. Mesure du 2026-08-29, 2 workers rendent 80/min.
EMB_WORKERS, EMB_BATCH = int(os.environ.get("LI_EMB_WORKERS", "2")), 8
FIT_WORKERS = 6
_W: dict = {}


# ---------------------------------------------------------------- embeddings
def _emb_init():
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"
    sys.path.insert(0, str(ROOT / "scripts" / "mcp"))
    import torch
    torch.set_num_threads(2)
    import ghost_server as gs
    gs._ensure_model()
    _W["gs"] = gs


def _emb_task(batch):
    gs = _W["gs"]
    return gs.embed(batch[0])[None, :] if len(batch) == 1 else gs.embed_batch(batch)


def embed_pool(texts, tag):
    import concurrent.futures as cf
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    batches = [order[k:k + EMB_BATCH] for k in range(0, len(order), EMB_BATCH)]
    vecs, done = {}, 0
    with cf.ProcessPoolExecutor(max_workers=EMB_WORKERS, initializer=_emb_init) as ex:
        futs = {ex.submit(_emb_task, [texts[i] for i in b]): b for b in batches}
        for fut in cf.as_completed(futs):
            b = futs[fut]
            res = fut.result()
            for kk, i in enumerate(b):
                vecs[i] = res[kk]
            done += len(b)
            print(f"  [{tag}] {done}/{len(texts)}", flush=True)
    return np.stack([vecs[i] for i in range(len(texts))]).astype("float64")


# ---------------------------------------------------------------- métriques
def auc(scores, labels):
    scores, labels = list(scores), list(labels)
    order = sorted(range(len(scores)), key=lambda k: scores[k])
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    rank_sum, i = 0.0, 0
    while i < len(order):
        j = i
        while j < len(order) and scores[order[j]] == scores[order[i]]:
            j += 1
        avg = (i + j + 1) / 2.0
        for k in range(i, j):
            if labels[order[k]] == 1:
                rank_sum += avg
        i = j
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def youden(p, y):
    thr, best = 0.5, -1.0
    for cand in np.unique(p):
        pred = p >= cand
        tp = float((pred & (y == 1)).sum()); fp = float((pred & (y == 0)).sum())
        fn = float(((~pred) & (y == 1)).sum()); tn = float(((~pred) & (y == 0)).sum())
        sens = tp / (tp + fn) if tp + fn else 0.0
        spec = tn / (tn + fp) if tn + fp else 0.0
        if sens + spec - 1 > best:
            best, thr = sens + spec - 1, float(cand)
    return thr


def bootstrap_ci(scores, y, n=1000, seed=42):
    rng = np.random.default_rng(seed)
    scores, y = np.asarray(scores), np.asarray(y)
    a = [v for v in (auc(scores[i].tolist(), y[i].tolist())
                     for i in (rng.integers(0, len(y), len(y)) for _ in range(n)))
         if v is not None]
    return float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))


# ---------------------------------------------------------------- fit
def _fit_init(xp, yp, gp):
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[v] = "1"
    _W["X"] = np.load(xp, mmap_mode="r")
    _W["y"] = np.load(yp)
    _W["g"] = np.load(gp, allow_pickle=True)


def _fit_task(chunk):
    from sklearn.linear_model import LogisticRegression
    X, y, g = _W["X"], _W["y"], _W["g"]
    out = {}
    for gg in chunk:
        te = g == gg
        tr = ~te
        if y[tr].sum() == 0 or y[tr].sum() == tr.sum():
            base = float(y[tr].mean()) if tr.sum() else 0.5
            out[gg] = (np.where(te)[0], np.full(int(te.sum()), base))
            continue
        clf = LogisticRegression(penalty="l2", C=C, solver="lbfgs", max_iter=5000)
        clf.fit(np.asarray(X[tr]), y[tr])
        out[gg] = (np.where(te)[0], clf.predict_proba(np.asarray(X[te]))[:, 1])
    return out


def loo(X, y, groups, folds, tag, paths):
    """Prédictions hors-pli. Aucune calibration ici : l'AUC se lit sur ce brut."""
    from sklearn.linear_model import LogisticRegression
    p = np.zeros(len(y))
    if X.shape[1] <= 8:
        for gg in folds:
            tr = groups != gg
            if y[tr].sum() == 0 or y[tr].sum() == tr.sum():
                p[~tr] = float(y[tr].mean()) if tr.sum() else 0.5
                continue
            clf = LogisticRegression(penalty="l2", C=C, solver="lbfgs",
                                     max_iter=5000).fit(X[tr], y[tr])
            p[~tr] = clf.predict_proba(X[~tr])[:, 1]
        return p
    import concurrent.futures as cf
    xp, yp, gp = paths
    np.save(xp, X)
    chunks = [folds[k:k + 4] for k in range(0, len(folds), 4)]
    with cf.ProcessPoolExecutor(max_workers=FIT_WORKERS, initializer=_fit_init,
                                initargs=(str(xp), str(yp), str(gp))) as ex:
        for res in ex.map(_fit_task, chunks):
            for gg, (rows, pv) in res.items():
                p[rows] = pv
    print(f"  [{tag}] LOO {len(folds)} plis terminé", flush=True)
    return p


def calibre_dans_le_pli(p_raw, y, groups, folds):
    """Isotonic et seuil de Youden ajustés HORS du pli qu'ils calibrent.

    Pour le pli `g` : ajustés sur les prédictions hors-pli des autres plis. Ils
    ne voient donc jamais les labels des points qu'ils transforment — c'est ce
    que l'erratum du 2026-08-25 exige, et ce que l'ancien `iso.fit(p_raw, y)`
    poolé violait.
    """
    from sklearn.isotonic import IsotonicRegression
    p_cal = np.zeros(len(y))
    seuils = {}
    for gg in folds:
        te = groups == gg
        tr = ~te
        if y[tr].sum() == 0 or y[tr].sum() == tr.sum():
            p_cal[te] = p_raw[te]
            seuils[gg] = 0.5
            continue
        iso = IsotonicRegression(out_of_bounds="clip").fit(p_raw[tr], y[tr])
        p_cal[te] = iso.predict(p_raw[te])
        seuils[gg] = youden(iso.predict(p_raw[tr]), y[tr])
    return p_cal, seuils


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=("w46", "p12", "p14"), required=True)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    trs = [json.loads(l) for l in SOURCES[a.corpus].read_text().splitlines() if l.strip()]
    print(f"corpus {a.corpus} : {len(trs)} transitions", flush=True)

    diff_txt, meta, y = [], [], []
    for t in trs:
        dec, rt, rf = t["declared"], set(t["red_to"]), set(t["red_from"])
        frac = len([x for x in dec if x in rf]) / max(1, len(dec))
        for d in dec:
            diff_txt.append(t["diff_to"])
            meta.append({"key": t["key"], "inst": t["instance"], "test": d,
                         "repo": t.get("repo", "?"),
                         "persist": 1.0 if d in rf else 0.0,
                         "frac": frac, "turn": float(t["turn_to"])})
            y.append(1 if d in rt else 0)
    y = np.asarray(y)
    print(f"paires : {len(y)} ({int(y.sum())} positives, "
          f"{100.0 * y.mean():.1f} %)", flush=True)

    uniq_d = sorted(set(diff_txt))
    uniq_t = sorted(set(m["test"] for m in meta))
    Ed, Et = {}, {}
    for cf_ in CACHES:
        if cf_.is_file():
            z = np.load(cf_, allow_pickle=True)
            if "diff_texts" in z.files:
                Ed.update(dict(zip(z["diff_texts"].tolist(), z["diff_vecs"])))
            if "test_texts" in z.files:
                Et.update(dict(zip(z["test_texts"].tolist(), z["test_vecs"])))
    todo_d = [x for x in uniq_d if x not in Ed]
    todo_t = [x for x in uniq_t if x not in Et]
    print(f"diffs {len(uniq_d)} ({len(todo_d)} à encoder) ; "
          f"tests {len(uniq_t)} ({len(todo_t)} à encoder)", flush=True)
    if todo_d:
        Ed.update(zip(todo_d, embed_pool(todo_d, "diffs")))
    if todo_t:
        Et.update(zip(todo_t, embed_pool(todo_t, "tests")))
    if todo_d or todo_t:
        anc = np.load(CACHES[-1], allow_pickle=True) if CACHES[-1].is_file() else None
        kd = (anc["diff_texts"].tolist() if anc is not None else []) + todo_d
        kt = (anc["test_texts"].tolist() if anc is not None else []) + todo_t
        np.savez_compressed(
            OUT / "emb-cache-p10.npz",
            diff_texts=np.array(kd, dtype=object),
            diff_vecs=np.stack([Ed[t] for t in kd]) if kd else np.zeros((0, 768)),
            test_texts=np.array(kt, dtype=object),
            test_vecs=np.stack([Et[t] for t in kt]) if kt else np.zeros((0, 768)))

    scal = np.array([[m["persist"], m["frac"], m["turn"]] for m in meta], dtype="float64")
    D = np.stack([Ed[d] for d in diff_txt]).astype("float64")
    T = np.stack([Et[m["test"]] for m in meta]).astype("float64")
    cos = np.einsum("ij,ij->i", D, T)[:, None]
    X_full = np.concatenate([D, T, cos, scal], axis=1)
    assert X_full.shape[1] == 1540, X_full.shape
    BRAS = {
        "complet (1540 d)": X_full,
        "Ed + scalaires": np.concatenate([D, cos, scal], axis=1),
        "Et + scalaires": np.concatenate([T, cos, scal], axis=1),
        "scalaires seuls": np.concatenate([cos, scal], axis=1),
        "persist seul": scal[:, :1],
    }

    # LOO PAR INSTANCE : deux trajectoires d'une même instance partagent le
    # ticket, le patch de test et les tests déclarés.
    groups = np.array([m["inst"] for m in meta])
    folds = sorted(set(groups.tolist()))
    print(f"X {X_full.shape} · LOO par INSTANCE : {len(folds)} plis", flush=True)
    paths = (OUT / f"_X-{a.corpus}.npy", OUT / f"_y-{a.corpus}.npy",
             OUT / f"_g-{a.corpus}.npy")
    np.save(paths[1], y)
    np.save(paths[2], groups, allow_pickle=True)

    res = {}
    for nom, Xr in BRAS.items():
        p = loo(Xr, y, groups, folds, nom, paths)
        a_raw = auc(p.tolist(), y.tolist())
        lo, hi = bootstrap_ci(p, y)
        p_cal, _ = calibre_dans_le_pli(p, y, groups, folds)
        res[nom] = {"auc_raw": a_raw, "ic95": [lo, hi],
                    "auc_cal_dans_le_pli": auc(p_cal.tolist(), y.tolist())}
        print(f"  {nom:20s} AUC(p_raw) {a_raw:.4f}  IC95 [{lo:.4f}, {hi:.4f}]", flush=True)
        np.save(OUT / f"p_raw-{a.corpus}-{nom.split()[0]}.npy", p)

    # CONTRÔLES NÉGATIFS. Deux permutations, qui ne testent PAS la même chose.
    #
    #  (a) GLOBALE — le lien X↔y est détruit partout. Si le pipeline rend
    #      encore de l'AUC, il en fabrique à partir de rien.
    #  (b) DANS L'INSTANCE — chaque instance garde SON taux de positifs, seul
    #      l'appariement interne est brouillé. Ce contrôle-là vise la réserve
    #      écrite au verdict P12 : une seule instance porte 26 % des positifs
    #      et les dépôts ont des taux de base très différents. Un modèle qui
    #      note en reconnaissant l'instance plutôt que la transition garderait
    #      de l'AUC ici, alors que (a) ne le verrait pas.
    negs = {}
    rng = np.random.default_rng(1234)
    y_glob = y[rng.permutation(len(y))]
    y_intra = y.copy()
    for gg in folds:
        idx = np.where(groups == gg)[0]
        y_intra[idx] = y[idx][rng.permutation(len(idx))]
    for tag, yp in (("globale", y_glob), ("dans l'instance", y_intra)):
        np.save(paths[1], yp)
        p_neg = loo(X_full, yp, groups, folds, f"négatif {tag}", paths)
        an = auc(p_neg.tolist(), yp.tolist())
        negs[tag] = an
        print(f"  {'NÉGATIF ' + tag:24s} AUC {an:.4f}  (attendu ≈ 0,50)", flush=True)
    a_neg = negs["globale"]
    np.save(paths[1], y)

    rap = {"at": datetime.now(UTC).isoformat(), "corpus": a.corpus,
           "n_transitions": len(trs), "n_paires": int(len(y)),
           "n_positives": int(y.sum()), "n_instances": len(folds),
           "loo": "instance", "auc_sur": "p_raw",
           "isotonic": "ajustée dans le pli", "bras": res,
           "controles_negatifs": negs}
    (OUT / f"p10-{a.corpus}.json").write_text(json.dumps(rap, ensure_ascii=False, indent=1))
    print(f"\nécrit : {OUT / f'p10-{a.corpus}.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
