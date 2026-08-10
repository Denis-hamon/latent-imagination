#!/usr/bin/env python3
"""S9 — smoke local : un causal-LLM LoRA-tuné (Qwen2.5-Coder-0.5B) prédit-il le
verdict F2P depuis (state, diff) MIEUX que l'énergie latente gelée ?

Doctrine :
- superviseur = verdict binaire chaîné (jamais le multi-hot comme source
  binaire — leçon 08-07d)
- goal-free : pas de gold (production)
- LOAO strict par tâche ; baseline = uxc énergie marge recalculée sur les mêmes
  folds (0.735 connu sur n=113)
- head = verdict-token : le prompt finit par "Answer:" et on supervise le token
  suivant, restreint à {PASS, FAIL} (CE sur la paire de logits — pas de CE
  vocab-large)
- SMOKE 0.5B : le gate v3 reste réservé au run 7B/32B sur node, protocole à
  déclarer avant ce run-là. Ici on répond : "un causal-LLM LoRA-é last-layers
  apprend-il QUELQUE CHOSE de ce format à n=113 ?"

Sortie : data/landing/act2-pilot/s9-smoke.json
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data" / "landing" / "act2-pilot"

PROMPT = ("You are given a code problem context and a patch. "
          "Decide whether applying the patch makes the failing tests pass.\n\n"
          "## Context\n{state}\n\n## Patch\n{diff}\n\n"
          "Answer with exactly one token: PASS or FAIL.\n\nAnswer:")


def wilson(k, n):
    z = 1.96
    p = k / max(1, n)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return max(0.0, c - h), min(1.0, c + h)


def uxc_baseline(rows, folds_eval):
    """Énergie latente uxc + marge médiane-train, LOAO, seulement sur les folds
    évalués (comparaison co-honorée)."""
    d = np.load(PILOT / "latent-pool.npz")
    def norm(A): return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
    E_s, E_d, E_g = norm(d["E_state"]), norm(d["E_diff"]), norm(d["E_goal"])
    cd, cg = norm(E_s + E_d), norm(E_s + E_g)
    energy = 1 - (cd * cg).sum(-1)
    y = np.array([r["y"] for r in rows])
    tasks = np.array([r["task"] for r in rows])
    pred = np.zeros(len(rows), int)
    conf = np.zeros(len(rows))
    for held in folds_eval:
        te = tasks == held
        thr = np.median(energy[~te])
        pred[te] = (energy[te] < thr).astype(int)
        conf[te] = np.abs(energy[te] - thr)
    return pred, conf


def fit_fold(model, tok, rows_tr, device, tid_pass, tid_fail,
             epochs=2, bs=8, lr=1e-4, seed=0):
    import torch
    from peft import LoraConfig, get_peft_model
    model = get_peft_model(model, LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.0, bias="none",
        target_modules=["q_proj", "v_proj"], task_type="CAUSAL_LM"))
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    classes = torch.tensor([tid_fail, tid_pass], device=device)  # index 0/1 = y
    for ep in range(epochs):
        order = np.random.default_rng(seed * 100 + ep).permutation(len(rows_tr))
        for i in range(0, len(order), bs):
            batch = [rows_tr[j] for j in order[i:i + bs]]
            texts = [PROMPT.format(state=r["state"][:1200], diff=r["diff"][:2200])
                     for r in batch]
            enc = tok(texts, padding=True, truncation=True, max_length=640,
                      return_tensors="pt").to(device)
            lab = torch.tensor([int(r["y"]) for r in batch], device=device)
            out = model(**enc, logits_to_keep=1)  # (B,1,V) — pas de (B,T,V) en MPS
            lg = out.logits[:, -1]  # left-padding : -1 = dernier token réel
            pair = lg[:, classes]                                # (B, 2)
            loss = torch.nn.functional.cross_entropy(pair.float(), lab)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
    return model


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=0, help="0 = LOAO complet")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--max-seconds-per-fold-est", type=float, default=75.0)
    args = ap.parse_args()

    rows = json.loads((PILOT / "latent-pool.json").read_text())
    y = np.array([r["y"] for r in rows])
    tasks = np.array([r["task"] for r in rows])
    folds_all = sorted(set(tasks))

    # baseline co-honorée (mêmes folds)
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-Coder-0.5B")
    tok.padding_side = "left"  # position -1 = fin réelle pour toutes les lignes
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tid_pass = tok(" PASS", add_special_tokens=False).input_ids[0] \
        if tok(" PASS", add_special_tokens=False).input_ids else None
    tid_pass = tok("PASS", add_special_tokens=False).input_ids[-1]
    tid_fail = tok("FAIL", add_special_tokens=False).input_ids[-1]

    # fold 0 = timing seul
    t0 = time.time()
    held = folds_all[0]
    te = tasks == held
    rows_tr = [r for r, m in zip(rows, ~te) if m]
    model = AutoModelForCausalLM.from_pretrained(
        "Qwen/Qwen2.5-Coder-0.5B", torch_dtype=torch.float16).to(device)
    model = fit_fold(model, tok, rows_tr, device, tid_pass, tid_fail,
                     epochs=args.epochs)
    dt0 = time.time() - t0
    print(f"fold 1 timing (incl. load modèle) : {dt0:.0f}s — "
          f"LOAO {len(folds_all)} folds ≈ {dt0*len(folds_all)/60:.0f} min")
    if args.folds == 0 and dt0 * len(folds_all) > 5400:
        print("BUDGET : >90 min estimés — smoke limité à --folds auto")
        args.folds = max(8, int(5400 / max(dt0, 1)))
        print(f"  → {args.folds} folds")
    folds = folds_all if args.folds == 0 else folds_all[: args.folds]

    pred = -np.ones(len(rows), int)
    conf = np.zeros(len(rows))
    model.eval()
    import torch as _t
    with _t.no_grad():
        for fi, held in enumerate(folds):
            if fi > 0:
                # refit à chaque fold (LOAO) — refit SOUS enable_grad car le bloc
                # externe est no_grad (backward sinon impossible, mesuré)
                del model
                if hasattr(_t.mps, "empty_cache"):
                    if device == "cuda":
                        _t.cuda.empty_cache()
                    if device == "mps":
                        _t.mps.empty_cache()
                with _t.enable_grad():
                    model = AutoModelForCausalLM.from_pretrained(
                        "Qwen/Qwen2.5-Coder-0.5B", torch_dtype=_t.float16).to(device)
                    model = fit_fold(model, tok,
                                     [r for r, m in zip(rows, tasks != held) if m],
                                     device, tid_pass, tid_fail, epochs=args.epochs,
                                     seed=fi)
                model.eval()
            te = tasks == held
            for j, r in zip(np.where(te)[0], [r for r, m in zip(rows, te) if m]):
                txt = PROMPT.format(state=r["state"][:1200], diff=r["diff"][:2200])
                enc = tok(txt, truncation=True, max_length=640,
                          return_tensors="pt").to(device)
                lg = model(**enc, logits_to_keep=1).logits[0, -1]
                pair = lg[[tid_fail, tid_pass]].float()
                p = float(torch.softmax(pair, dim=-1)[1])
                pred[j] = int(p > 0.5)
                conf[j] = abs(p - 0.5)
            if fi % 10 == 0:
                print(f"  fold {fi+1}/{len(folds)}", flush=True)

    sel = np.isin(tasks, folds)
    pred_b, conf_b = uxc_baseline(rows, folds)
    res = {}
    for name, pr, cf in (("lora-0.5B", pred, conf), ("uxc-énergie", pred_b, conf_b)):
        m = sel
        k = int((pr[m] == y[m]).sum())
        acc = (pr[m] == y[m]).mean()
        lo, hi = wilson(k, int(m.sum()))
        # AUC sur p implicite : conf est la marge; on stocke juste acc + courbe
        order = np.argsort(-cf[m])
        ym, pm = y[m], pr[m]
        curve = []
        for cov in (1.0, 0.5, 0.25):
            mm = max(1, int(round(m.sum() * cov)))
            s2 = order[:mm]
            kk = int((pm[s2] == ym[s2]).sum())
            l2, h2 = wilson(kk, mm)
            curve.append({"coverage": cov, "n": mm, "acc": kk / mm,
                          "wilson95": [l2, h2]})
        res[name] = {"acc": float(acc), "wilson95": [lo, hi], "n": int(m.sum()),
                     "curve": curve}
        print(f"\n{name}: acc {acc:.3f} [{lo:.3f},{hi:.3f}] (n={int(m.sum())})")
        for c in curve:
            print(f"  cov {c['coverage']:4.0%} n={c['n']:3d} acc {c['acc']:.3f}")

    out = {"smoke": True, "model": "Qwen/Qwen2.5-Coder-0.5B + LoRA r8 q,v",
           "folds_evaluated": len(folds), "folds_total": len(folds_all),
           "epochs": args.epochs, "results": res,
           "note": "gate v3 réservé au run 7B/32B node — ceci mesure l'apprentissage"}
    (PILOT / "s9-smoke.json").write_text(json.dumps(out, indent=1))
    print(f"\nartefact : {PILOT / 's9-smoke.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
