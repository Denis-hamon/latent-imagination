#!/usr/bin/env python3
"""S7 — pool v6 : ajout des candidats boltzmann-e1 labellisés (0 call galere).

S6/S6b (node WMEL-gpu-strong, pure exécution docker) ont produit les labels des
128 candidats E1 (4 × 32 tâches frozen32, générés T=0.7 le 08-09) : 32 applicables
(strict 14 + récupérés sanitize/recount 18), 13 F2P verts — tous avec P2P verts
(f2p&p2p vérifié dans les labels). Mixture DÉCLARÉE : distribution best-of-4 brute,
sans retry instrumenté, inclut les diffs récupérés (recovered=true dans les labels).

Protocole identique à S5 : dédup (task, sha256 diff) contre v5, state/gold depuis
pilot-tasks frozen32 + control-gold racine, embed incrémental uxc-base gelé,
réévaluation GOLD+marge et GxF+platt λ=1 en LOAO-strict.

Sorties : latent-pool-v6.json/.npz + s7-boltzmann-extension.json
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


def collect_boltzmann(existing_keys):
    """Bolztman applicables STRICTS uniquement.

    Mesuré (addendum 08-10g) : les 18 recovered (diffs réparés par
    sanitize/recount) ont une énergie latente au niveau du hasard
    (AUC 0.543, sous-éval interne) — leur forme textuelle ne correspond
    plus à ce que le modèle a écrit. Ils empoisonnent la queue
    haute-confiance (cov@≥0.95 : 0.939@20% → 0 avec eux). Exclus ici ;
    conservés dans les labels pour la traçabilité, marqués recovered=true.
    """
    ptasks = {t["instance_id"]: t for t in
              json.loads((PILOT / "pilot-tasks-frozen32.json").read_text())}
    ldir = PILOT / "boltzmann-e1" / "labels"
    rows, seen = [], set()
    excluded_recovered = 0
    for lf in sorted(ldir.glob("*.json")):
        j = json.loads(lf.read_text())
        if not j.get("patch_applied"):
            continue
        if j.get("recovered"):
            excluded_recovered += 1
            continue
        iid, k = j["task"], j["cand"]
        diff = (PILOT / "boltzmann-e1" / f"{j['diff_file']}").read_text()
        if not diff.strip():
            continue
        key = dkey(iid, diff)
        if key in existing_keys or key in seen:
            continue
        seen.add(key)
        t = ptasks[iid]
        goldf = PILOT / "control-gold" / iid.replace("/", "_") / "gold.diff"
        rows.append({"task": iid, "arm": f"cand{k}", "campaign": "boltzmann-e1",
                     "recovered": bool(j.get("recovered")),
                     "state": (t["problem"][:1200] + "\n"
                               + "; ".join(map(str, t["f2p"][:6]))),
                     "diff": diff,
                     "gold": goldf.read_text() if goldf.is_file() else "",
                     "y": 1 if j.get("f2p_pass") else 0})
    print(f"  (exclus : {excluded_recovered} recovered — voir docstring)")
    return rows


def eval_gold_and_gxf(E_s, E_d, E_g, y, tasks):
    E_ns, E_nd, E_ng = norm(E_s), norm(E_d), norm(E_g)
    cd = norm(E_ns + E_nd)
    energy = 1.0 - (cd * norm(E_ns + E_ng)).sum(-1)
    n = len(y)
    out = {}

    pred, conf = np.zeros(n, int), np.zeros(n)
    predc, confc, sco = np.zeros(n, int), np.zeros(n), np.zeros(n)
    for held in sorted(set(tasks)):
        te, tr = tasks == held, tasks != held
        e_tr, e_te, y_tr = energy[tr], energy[te], y[tr]
        thr = np.median(e_tr)
        pred[te] = (e_te < thr).astype(int)
        conf[te] = np.abs(e_te - thr)
        # GxF+platt λ=1 (champion S3), fit train-only
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
        predc[te] = (p > 0.5).astype(int)
        confc[te] = np.abs(p - 0.5)
        sco[te] = p

    maj = max(y.mean(), 1 - y.mean())
    for name, (sc, pr, cf) in {"GOLD+margin": (-energy, pred, conf),
                               "GxF+platt": (sco, predc, confc)}.items():
        curve = []
        order = np.argsort(-cf)
        for cov in COVERAGES:
            m = max(1, round(n * cov))
            sel = order[:m]
            k = int((pr[sel] == y[sel]).sum())
            lo, hi = wilson(k, m)
            curve.append({"coverage": cov, "n": m, "acc": k / m,
                          "wilson95": [lo, hi]})
        best = 0.0
        for c in curve:
            if c["acc"] >= TARGET_ACC and c["wilson95"][0] > maj:
                best = max(best, c["coverage"])
        out[name] = {"auc": auc(sc[y == 1], sc[y == 0]),
                     "acc_loao": curve[0]["acc"],
                     "max_cov_at_target": best, "curve": curve}
    return out


def main() -> int:
    base_rows = json.loads((PILOT / "latent-pool-v5.json").read_text())
    existing = {dkey(r["task"], r["diff"]) for r in base_rows}
    new_rows = collect_boltzmann(existing)
    pos_new = sum(r["y"] for r in new_rows)
    rec_new = sum(1 for r in new_rows if r.get("recovered"))
    print(f"pool v5 : {len(base_rows)} | boltzmann applicables après dédup : "
          f"{len(new_rows)} (positifs {pos_new}, recovered {rec_new})")
    if not new_rows:
        return 1

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

    E_new = {k: batched([r[f] for r in new_rows])
             for k, f in (("E_state", "state"), ("E_diff", "diff"),
                          ("E_goal", "gold"))}
    d0 = np.load(PILOT / "latent-pool-v5.npz")
    E_s = np.concatenate([d0["E_state"], E_new["E_state"]])
    E_d = np.concatenate([d0["E_diff"], E_new["E_diff"]])
    E_g = np.concatenate([d0["E_goal"], E_new["E_goal"]])
    rows = base_rows + new_rows
    np.savez_compressed(PILOT / "latent-pool-v6.npz",
                        E_state=E_s, E_diff=E_d, E_goal=E_g)
    (PILOT / "latent-pool-v6.json").write_text(json.dumps(rows, indent=1))

    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    res = {"n": len(rows), "n_new": len(new_rows), "pos_new": pos_new,
           "recovered_new": rec_new, "pos": int(y.sum()),
           "tasks": len(set(tasks)),
           "sources": {c: sum(1 for r in rows if r.get("campaign") == c)
                       for c in sorted({r.get("campaign") for r in rows})}}
    res.update(eval_gold_and_gxf(E_s, E_d, E_g, y, tasks))

    maj = max(y.mean(), 1 - y.mean())
    print(f"\n===== S7 — pool v6 n={len(rows)} ({res['pos']} positifs, "
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

    (PILOT / "s7-boltzmann-extension.json").write_text(
        json.dumps(res, indent=1, default=float))
    print("\nartefacts : latent-pool-v6.json/.npz, s7-boltzmann-extension.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
