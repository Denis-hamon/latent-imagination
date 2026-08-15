#!/usr/bin/env python3
"""S4 — swap d'encodeur GELÉ : la famille uniXCoder-base est-elle le plafond ?

Leçon E2 (mesurée) : fine-tuner l'encodeur DÉTRUIT le signal (AUC 0.513). Mais
le choix d'uniXCoder-base était une convenance node-GPU, pas une mesure. Ici :
même pool, même troncature 512, même extraction, zéro entraînement — seul
l'encodeur gelé change.

Candidats (pooling = reco officielle de chacun, asymétrie déclarée) :
  - microsoft/unixcoder-base       CONTRÔLE : doit reproduire AUC 0.817 / acc
                                   LOAO 0.735 / S1 1.000@25% (artefacts act2)
  - microsoft/unixcoder-large      même famille, ~x4 params
  - jinaai/jina-embeddings-v2-base-code  code-spécifique récent (mean pooling)

Métriques par encodeur (protocole identique à 08-09b / S1) : AUC énergie latente
no-train, acc LOAO seuil médiane-train, courbe couverture/acc, cov@≥0.95.

Sorties : data/landing/act2-pilot/latent-pool-<slug>.npz + s4-encoder-swap.json
Environnement : .venv-embed (torch+transformers), CPU/MPS local, 0 call galere.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"

CANDIDATES = [
    {"slug": "uxc-base", "hf": "microsoft/unixcoder-base", "pooling": "cls",
     "control": True},
    {"slug": "codebert", "hf": "microsoft/codebert-base", "pooling": "cls"},
    {"slug": "u5p-code", "hf": "Salesforce/codet5p-110m-embedding", "pooling": "cls"},
    {"slug": "jina-code", "hf": "jinaai/jina-embeddings-v2-base-code",
     "pooling": "mean"},
]
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


def embed_all(hf, pooling, texts_by_kind, device):
    import torch
    from transformers import AutoModel, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(hf, trust_remote_code=True)
    model = AutoModel.from_pretrained(hf, trust_remote_code=True).to(device).eval()

    def batched(texts, bs=16):
        out = []
        for i in range(0, len(texts), bs):
            tb = tok(texts[i:i + bs], padding=True, truncation=True,
                     max_length=512, return_tensors="pt")
            with torch.no_grad():
                res = model(**{k: t.to(device) for k, t in tb.items()})
                if isinstance(res, torch.Tensor):  # ex. codet5p : embedding direct
                    out.append(res.float().cpu().numpy())
                    continue
                hs = res.last_hidden_state
                if pooling == "cls":
                    v = hs[:, 0]
                else:  # mean pooling masqué
                    m = tb["attention_mask"].to(device).unsqueeze(-1)
                    v = (hs * m).sum(1) / m.sum(1).clamp(min=1)
            out.append(v.float().cpu().numpy())
        return np.concatenate(out)

    return {k: batched(v) for k, v in texts_by_kind.items()}


def evaluate(E_s, E_d, E_g, y, tasks):
    """Énergie latente + courbe S1, protocole identique à 08-09b / S1."""
    E_s, E_d, E_g = norm(E_s), norm(E_d), norm(E_g)
    cd, cg = norm(E_s + E_d), norm(E_s + E_g)
    energy = 1.0 - (cd * cg).sum(-1)
    n = len(y)
    pred = np.zeros(n, dtype=int)
    conf = np.zeros(n)
    for held in sorted(set(tasks)):
        te = tasks == held
        thr = np.median(energy[~te])
        pred[te] = (energy[te] < thr).astype(int)
        conf[te] = np.abs(energy[te] - thr)
    maj = max(y.mean(), 1 - y.mean())
    curve = []
    order = np.argsort(-conf)
    for cov in COVERAGES:
        m = max(1, round(n * cov))
        sel = order[:m]
        k = int((pred[sel] == y[sel]).sum())
        lo, hi = wilson(k, m)
        curve.append({"coverage": cov, "n": m, "acc": k / m,
                      "wilson95": [lo, hi]})
    best = 0.0
    for c in curve:
        if c["acc"] >= TARGET_ACC and c["wilson95"][0] > maj:
            best = max(best, c["coverage"])
    return {"auc_gold": auc((-energy)[y == 1], (-energy)[y == 0]),
            "acc_loao": curve[0]["acc"], "max_cov_at_target": best,
            "curve": curve}


def main() -> int:
    import torch
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    rows = json.loads((PILOT / "latent-pool.json").read_text())
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    texts = {"E_state": [r["state"] for r in rows],
             "E_diff": [r["diff"] for r in rows],
             "E_goal": [r["gold"] for r in rows]}
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only and not any(c["slug"] == only for c in CANDIDATES):
        print(f"slug inconnu : {only} — candidats : "
              f"{[c['slug'] for c in CANDIDATES]}")
        return 2

    artefact = PILOT / "s4-encoder-swap.json"
    out = {"n": len(rows), "device": device, "candidates": {}}
    if artefact.is_file():  # fusion : ne jamais perdre un candidat déjà mesuré
        prev = json.loads(artefact.read_text())
        out["candidates"] = prev.get("candidates", {})
        out["positive_control"] = prev.get("positive_control")
    for c in CANDIDATES:
        if only and c["slug"] != only:
            continue
        t0 = time.time()
        emb = embed_all(c["hf"], c["pooling"], texts, device)
        np.savez_compressed(PILOT / f"latent-pool-{c['slug']}.npz", **emb)
        res = evaluate(emb["E_state"], emb["E_diff"], emb["E_goal"], y, tasks)
        res["seconds"] = round(time.time() - t0, 1)
        out["candidates"][c["slug"]] = res
        print(f"\n== {c['slug']} ({c['hf']}, pooling={c['pooling']}) "
              f"[{res['seconds']}s] ==")
        print(f"  AUC GOLD no-train : {res['auc_gold']:.3f}")
        print(f"  acc LOAO (cov 1)  : {res['acc_loao']:.3f}")
        print(f"  cov@>={TARGET_ACC} (lb Wilson > maj) : {res['max_cov_at_target']:.0%}")
        for cv in res["curve"]:
            print(f"    cov {cv['coverage']:4.0%} | n={cv['n']:3d} | acc {cv['acc']:.3f} "
                  f"[{cv['wilson95'][0]:.3f},{cv['wilson95'][1]:.3f}]")

    # contrôle positif : uxc-base doit être à ~0.817
    if "uxc-base" in out["candidates"]:
        a = out["candidates"]["uxc-base"]["auc_gold"]
        ok = abs(a - 0.817) < 0.01
        print(f"\ncontrôle positif (uxc-base AUC == 0.817 ± 0.01) : "
              f"{'OK' if ok else 'DÉRIVE ' + str(round(a, 3))}")
        out["positive_control"] = {"expected": 0.817, "got": a, "ok": ok}

    (artefact).write_text(json.dumps(out, indent=1))
    print(f"\nartefact : {artefact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
