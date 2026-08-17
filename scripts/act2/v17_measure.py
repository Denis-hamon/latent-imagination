#!/usr/bin/env python3
"""Fenêtre v17 — mesure PAIRÉE goal-vs-cd sur les 312 lignes exportées.
Node GPU. Recettes : s11._loao_f1_features (cd) et s11.loao_energy/report
(ancre v6, axe goal) — identiques aux promotions, aucune variante.
Run (node): .venv/bin/python scripts/act2/v17_measure.py <v17-rows.json>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s11)


def embed_node(texts: list[str]) -> np.ndarray:
    import os

    import torch
    import transformers as tf
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

    def _fphi(heads, n_heads, head_size, already):
        mask = torch.ones(n_heads, head_size)
        heads = set(heads) - already
        for h in heads:
            h -= sum(1 if oh < h else 0 for oh in already)
            mask[h] = 0
        f = mask.view(-1).contiguous().eq(1)
        return heads, torch.arange(f.size(0))[f].long()
    tf.pytorch_utils.find_pruneable_heads_and_indices = _fphi
    if not hasattr(tf.PreTrainedModel, "get_head_mask"):
        tf.PreTrainedModel.get_head_mask = (
            lambda self, hm, nl, is_attention_chunked=False: [None] * nl)
    from transformers import AutoConfig, AutoModel, AutoTokenizer
    cid = "jinaai/jina-embeddings-v2-base-code"
    cfg = AutoConfig.from_pretrained(cid, trust_remote_code=True)
    for a, v in (("is_decoder", False), ("use_cache", False), ("is_encoder_decoder", False),
                 ("tie_word_embeddings", False), ("add_cross_attention", False),
                 ("chunk_size_feed_forward", 0), ("cross_attention_hidden_size", None)):
        if not hasattr(cfg, a):
            setattr(cfg, a, v)
    tok = AutoTokenizer.from_pretrained(cid, trust_remote_code=True)
    model = AutoModel.from_pretrained(cid, config=cfg, trust_remote_code=True).eval()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(dev)
    out = []
    for i, t in enumerate(texts):
        tb = tok([t], padding=True, truncation=True, max_length=8192 if "jina" in cid else 512,
                 return_tensors="pt")
        kw = {"token_type_ids": torch.zeros_like(tb["input_ids"])}
        with torch.no_grad():
            lh = model(**{k: v.to(dev) for k, v in tb.items()},
                       **{k: v.to(dev) for k, v in kw.items()}).last_hidden_state
        idx = int(tb["attention_mask"].sum(1)[0]) - 1
        v = lh[0, idx].cpu().numpy().astype(np.float64)
        out.append(v / (np.linalg.norm(v) + 1e-9))
        if (i + 1) % 100 == 0:
            print(f"  embed {i + 1}/{len(texts)}", flush=True)
    return np.stack(out)


def main() -> int:
    rows = json.loads(Path(sys.argv[1]).read_text())
    cache = Path(sys.argv[1]).with_suffix(".emb.npz")
    y = np.array([r["y"] for r in rows])
    tasks = np.array([r["task"] for r in rows])
    if cache.is_file():
        d = np.load(cache)
        Es, Ed, Eg = d["Es"], d["Ed"], d["Eg"]
        print("cache embeddings OK")
    else:
        Es = embed_node([r["state"] for r in rows])
        Ed = embed_node([r["diff"][:8000] for r in rows])
        Eg = embed_node([r["gold"][:8000] for r in rows])
        np.savez_compressed(cache, Es=Es, Ed=Ed, Eg=Eg)
    cd = s11.norm(s11.norm(Es) + s11.norm(Ed))
    cg = s11.norm(s11.norm(Es) + s11.norm(Eg))
    # --- A1 : axe cd seul — RECETTE SERVIE (conformal_calibrate : f1 LOAO + report) ---
    f1 = s11._loao_f1_features(cd, tasks, y)
    thr = float(np.median(f1))
    pred_c = (f1 > thr).astype(int)
    rep_cd = s11.report("V17 CD-ONLY", pred_c, np.abs(f1 - thr), f1, y,
                        max(y.mean(), 1 - y.mean()))
    # --- A2 : axe goal (recette ancre v6 : loao_energy + report) ---
    pred_g, conf_g, sco_g = s11.loao_energy(cd, cg, y, tasks)
    rep = s11.report("V17 GOAL", pred_g, conf_g, sco_g, y, max(y.mean(), 1 - y.mean()))
    # bootstrap IC95 de la différence d'AUC (paires de lignes, 1000 tirages)
    # bootstrap IC95 de la différence d'AUC : paire (ligne) résampling sur les
    # deux scores LOAO (sco_g goal vs f1 cd), AUC rank recalculée par tirage
    rng = np.random.default_rng(17)
    diffs = []
    for _ in range(1000):
        ix = rng.integers(0, len(y), len(y))
        sg, sc, yg = sco_g[ix], f1[ix], y[ix]
        if len(np.unique(yg)) < 2:
            continue
        a_g = s11.auc(sg[yg == 1], sg[yg == 0])
        a_c = s11.auc(sc[yg == 1], sc[yg == 0])
        diffs.append(a_g - a_c)
    lo, hi = float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))
    out = {
        "window": "v17-ts-gold", "anchor": "7072deb98348a6d0",
        "population": {"n": len(rows), "positifs": int(y.sum()),
                       "n_tickets": len(set(tasks)),
                       "rows_sha256_16": sha256(json.dumps(
                           [r["key"] for r in rows]).encode()).hexdigest()[:16]},
        "A1_auc_cd_recette_servie": round(float(rep_cd["auc"]), 4),
        "A1_cov95_regime": rep_cd.get("max_cov"),
        "A2_goal_axis": {k: rep[k] for k in ("auc", "acc100", "max_cov") if k in rep},
        "IC95_diff_goal_moins_cd": [round(lo, 4), round(hi, 4)],
        "disclosure": "run1 invalide (recette ext ad hoc, AUC 0.0636 inversée) ; run2 bug "
                      "formule IC (double soustraction AUC_cd, verdict erroné détecté au "
                      "contrôle avant rapport) ; run3 = quantiles directs des diffs bootstrap ; "
                      "recettes A1 (f1 LOAO+report, servie) et A2 (loao_energy+report, ancre v6) exactes",
        "grille": {"cond": "AUC_goal >= AUC_cd + 0.05 ET IC95 diff borne basse >= 0",
                   "auc_goal": round(float(rep["auc"]), 4),
                   "auc_cd": round(float(rep_cd["auc"]), 4),
                   "delta": round(float(rep["auc"]) - float(rep_cd["auc"]), 4)},
    }
    valid = float(rep["auc"]) >= float(rep_cd["auc"]) + 0.05 and lo >= 0
    out["grille"]["verdict"] = "VALIDÉ" if valid else "CLOS"
    print(json.dumps(out, indent=1, ensure_ascii=False))
    Path(ROOT / "governance" / "act2" / "arm-artifacts" /
         "arm-v17-ts-gold-mesure-2026-08-17.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
