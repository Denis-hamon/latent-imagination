#!/usr/bin/env python3
"""S5 — extension du pool latent à 0 call galere : récupération des patchs rct-v1.

Constat d'audit (2026-08-10) :
- les fenêtres pilotes (frozen32 v1/v2/v3, extension-128) n'ont PAS persisté les
  raw replies → les 281 slots non-applicables sont irrécupérables sans nouvel
  appel modèle ;
- les fenêtres RCT écartées (discarded-window-1..3) ont les raw replies mais
  aucune exécution conservée → labels impossibles sans node docker ;
- e1-boltzmann : 128 candidats générés mais mapping candidat→verdict non
  persisté (seuls 2 patchs gagnants identifiés, à ~candK près) → écarté ;
- rct-v1/results (série scellée) : 28 slots b0/b1, 21 patchs APPLIQUÉS avec
  run-result (f2p_pass, p2p_pass) — AJOUTABLES tels quels au pool latent.

Protocole : dédup stricte (task, sha256 du diff normalisé) contre les 113 rows
existantes ; construction state/gold identique à embed_pool.py (problem[:1200]
+ f2p[:6] ; gold = control-gold racine, mêmes 32 tâches frozen32) ; embed
incrémental uniXCoder-base gelé (même encodeur, même extraction CLS 512 —
cohérence avec latent-pool.npz vérifiée au bit près par S4) ; mixture de
génération élargie (b0 = 2e chance neutre, b1 = contexte WM) DÉCLARÉE ici —
LOAO par tâche rend la fuite impossible (fold = toute la tâche, tous ses patchs).

Sorties : latent-pool-v5.json/.npz + s5-extension.json ; réévaluation GOLD
(énergie no-train) + GxF+platt λ=1 (champion S3) sur le pool étendu.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"
COVERAGES = (1.0, 0.75, 0.5, 0.4, 0.3, 0.25, 0.2, 0.1)
TARGET_ACC = 0.95


def norm(A):
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def wilson(k, n):
    z = 1.96
    p = k / max(1, n)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return max(0.0, c - h), min(1.0, c + h)


def auc(succ, fail):
    if not len(succ) or not len(fail):
        return float("nan")
    d = succ[:, None] - fail[None, :]
    return float((np.sum(d > 0) + 0.5 * np.sum(d == 0)) / d.size)


def logreg_fit(X, y, lam=1.0, iters=200):
    Xb = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(Xb.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(Xb @ w)))
        g = Xb.T @ (p - y) + lam * w
        W = p * (1 - p) + 1e-9
        H = (Xb * W[:, None]).T @ Xb + lam * np.eye(Xb.shape[1])
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def logreg_predict(X, w):
    return 1.0 / (1.0 + np.exp(-(np.column_stack([np.ones(len(X)), X]) @ w)))


def dkey(task, diff):
    return task + "|" + hashlib.sha256(diff.strip().encode()).hexdigest()[:16]


def collect_rct(existing_keys):
    tasks = {t["instance_id"]: t
             for t in json.loads((PILOT / "rct-v1" / "pilot-tasks.json").read_text())}
    rows, seen = [], set()
    for slot in sorted((PILOT / "rct-v1" / "results").glob("*")):
        mf, pf, rf = slot / "meta.json", slot / "patch.diff", slot / "run-result.json"
        if not (mf.is_file() and pf.is_file() and rf.is_file()):
            continue
        ptxt = pf.read_text()
        if not ptxt.strip():
            continue
        m = json.loads(mf.read_text())
        r = json.loads(rf.read_text())
        if not r.get("patch_applied"):
            continue
        t = tasks[m["task"]]
        key = dkey(m["task"], ptxt)
        if key in existing_keys or key in seen:
            continue
        seen.add(key)
        goldf = PILOT / "control-gold" / m["task"].replace("/", "_") / "gold.diff"
        rows.append({"task": m["task"], "arm": "rct-" + m["arm"],
                     "campaign": "rct-v1",
                     "state": (t["problem"][:1200] + "\n"
                               + "; ".join(map(str, t["f2p"][:6]))),
                     "diff": ptxt,
                     "gold": goldf.read_text() if goldf.is_file() else "",
                     "y": 1 if r.get("f2p_pass") else 0})
    return rows


def eval_energy(E_s, E_d, E_g, y, tasks):
    E_s, E_d, E_g = norm(E_s), norm(E_d), norm(E_g)
    cd, cg = norm(E_s + E_d), norm(E_s + E_g)
    energy = 1.0 - (cd * cg).sum(-1)
    n = len(y)
    pred, conf = np.zeros(n, int), np.zeros(n)
    for held in sorted(set(tasks)):
        te = tasks == held
        thr = np.median(energy[~te])
        pred[te] = (energy[te] < thr).astype(int)
        conf[te] = np.abs(energy[te] - thr)
    return pack((-energy), pred, conf, y, energy=energy)


def eval_gxf_platt(energy, cd, y, tasks):
    """Champion S3 : logreg 2D [GOLD, F1] λ=1, fit train du fold, LOAO strict."""
    n = len(y)
    pred, conf, sco = np.zeros(n, int), np.zeros(n), np.zeros(n)
    for held in sorted(set(tasks)):
        te, tr = tasks == held, tasks != held
        e_tr, e_te, y_tr = energy[tr], energy[te], y[tr]
        cd_tr = cd[tr]
        sims = cd[te] @ cd_tr.T
        f1_te = (1 - sims[:, y_tr == 0]).min(1) - (1 - sims[:, y_tr == 1]).min(1)
        f1_tr = ((1 - cd_tr @ cd_tr[y_tr == 0].T).min(1)
                 - (1 - cd_tr @ cd_tr[y_tr == 1].T).min(1))
        Ftr = np.column_stack([-e_tr, f1_tr])
        Fte = np.column_stack([-e_te, f1_te])
        mu, sd = Ftr.mean(0), Ftr.std(0) + 1e-9
        w = logreg_fit((Ftr - mu) / sd, y_tr)
        p = logreg_predict((Fte - mu) / sd, w)
        pred[te] = (p > 0.5).astype(int)
        conf[te] = np.abs(p - 0.5)
        sco[te] = p
    return pack(sco, pred, conf, y)


def pack(score, pred, conf, y, energy=None):
    n = len(y)
    maj = max(y.mean(), 1 - y.mean())
    curve = []
    order = np.argsort(-conf)
    for cov in COVERAGES:
        m = max(1, round(n * cov))
        sel = order[:m]
        k = int((pred[sel] == y[sel]).sum())
        lo, hi = wilson(k, m)
        curve.append({"coverage": cov, "n": m, "acc": k / m, "wilson95": [lo, hi]})
    best = 0.0
    for c in curve:
        if c["acc"] >= TARGET_ACC and c["wilson95"][0] > maj:
            best = max(best, c["coverage"])
    return {"auc": auc(score[y == 1], score[y == 0]), "acc_loao": curve[0]["acc"],
            "max_cov_at_target": best, "curve": curve}


def main() -> int:
    base_rows = json.loads((PILOT / "latent-pool.json").read_text())
    existing = {dkey(r["task"], r["diff"]) for r in base_rows}
    new_rows = collect_rct(existing)
    print(f"pool actuel : {len(base_rows)} | candidats rct-v1 appliqués, "
          f"après dédup : {len(new_rows)} "
          f"(positifs : {sum(r['y'] for r in new_rows)})")
    if not new_rows:
        print("rien à ajouter")
        return 1

    # embed incrémental (uxc-base gelé, identique au pool de référence)
    import torch
    from transformers import AutoModel, AutoTokenizer
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    model = AutoModel.from_pretrained("microsoft/unixcoder-base").to(device).eval()

    def batched(texts, bs=16):
        out = []
        for i in range(0, len(texts), bs):
            tb = tok(texts[i:i + bs], padding=True, truncation=True,
                     max_length=512, return_tensors="pt")
            with torch.no_grad():
                v = model(**{k: t.to(device) for k, t in tb.items()}).last_hidden_state[:, 0]
            out.append(v.float().cpu().numpy())
        return np.concatenate(out)

    E_new = {k: batched([r[field] for r in new_rows])
             for k, field in (("E_state", "state"), ("E_diff", "diff"),
                              ("E_goal", "gold"))}
    d0 = np.load(PILOT / "latent-pool.npz")
    E_s = np.concatenate([d0["E_state"], E_new["E_state"]])
    E_d = np.concatenate([d0["E_diff"], E_new["E_diff"]])
    E_g = np.concatenate([d0["E_goal"], E_new["E_goal"]])
    rows = base_rows + new_rows
    np.savez_compressed(PILOT / "latent-pool-v5.npz",
                        E_state=E_s, E_diff=E_d, E_goal=E_g)
    (PILOT / "latent-pool-v5.json").write_text(json.dumps(rows, indent=1))

    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    res = {"n": len(rows), "n_new": len(new_rows),
           "pos": int(y.sum()), "tasks": len(set(tasks)),
           "sources": {c: sum(1 for r in rows if r.get("campaign") == c)
                       for c in sorted({r.get("campaign") for r in rows})}}

    # évaluation : GOLD seul + champion S3, protocole identique
    E_ns, E_nd, E_ng = norm(E_s), norm(E_d), norm(E_g)
    cd = norm(E_ns + E_nd)
    energy = 1.0 - (cd * norm(E_ns + E_ng)).sum(-1)
    res["GOLD+margin"] = eval_energy(E_s, E_d, E_g, y, tasks)
    res["GxF+platt"] = eval_gxf_platt(energy, cd, y, tasks)

    maj = max(y.mean(), 1 - y.mean())
    print(f"\n===== S5 — pool étendu n={len(rows)} ({res['pos']} positifs, "
          f"{res['tasks']} tâches, majorité {maj:.3f}) =====")
    print(f"sources : {res['sources']}")
    for name, a in res.items():
        if not isinstance(a, dict) or "curve" not in a:
            continue
        print(f"\n{name} : AUC {a['auc']:.3f} | acc100 {a['acc_loao']:.3f} | "
              f"cov@>={TARGET_ACC} {a['max_cov_at_target']:.0%}")
        for c in a["curve"]:
            print(f"  cov {c['coverage']:4.0%} | n={c['n']:3d} | acc {c['acc']:.3f} "
                  f"[{c['wilson95'][0]:.3f},{c['wilson95'][1]:.3f}]")

    (PILOT / "s5-extension.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"\nartefacts : latent-pool-v5.json/.npz, s5-extension.json dans {PILOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
