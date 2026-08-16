#!/usr/bin/env python3
"""Story 13.3 — sonde de projection adversariale famille (0 appel, node unique NFR-C1).

Hypothèse : forcer une petite projection des embeddings gelés à prédire
l'OUTCOME sans pouvoir prédire la FAMILLE (gradient reversal) produit un espace
plus invariant par famille → meilleur ext-LOAO que la géométrie courante
(baseline scellée 0.5477, gate candidat ≥ 0.5977, home-guard in-family ≥ 0.6494).

CONFIG ÉPINGLÉE ICI AVANT TOUT RUN (amendment-only ensuite — gates 13.1) :
  hidden h=12 (768×12 + 12×2 ≈ 9.2k params ≈ 1e4, la capacité annoncée),
  λ_adv = 1.0, lr = 1e-3, epochs = 300, batch plein, seed 20260805.
  Un seul point de config : pas de grille, pas de sélection contre l'eval.

Validation : leave-one-family-out STRICT — pour chaque famille, la sonde est
ENTRAÎNÉE sur les autres familles et ÉVALUÉE sur la held-out (c'est le fold
ext-LOAO ; le seuil de décision est la médiane des scores du TRAIN de chaque
fold, jamais le pool complet).

Précédent cité (AC) : la destruction E2/S9 — une capacité non bornée peut
détruire le home regime pour gagner du transfert ; ici capacité ≈1e4 params
et garde-home mesurée (in-family LOAO co-rapporté).

Sortie : governance/act2/arm-artifacts/ext-loao-candidate-advprobe-v10.json
Run: uv run --package li-probe --extra ml python scripts/act3/probe_adversarial.py
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
OUT = ROOT / "governance" / "act2" / "arm-artifacts" / "ext-loao-candidate-advprobe-v10.json"

_spec = importlib.util.spec_from_file_location("s11", ROOT / "scripts" / "act2" / "s11_ext_pool.py")
s11 = importlib.util.module_from_spec(_spec)
sys.modules["s11_ext_pool"] = s11
_spec.loader.exec_module(s11)

# ---------------- config épinglée (pré-run, amendment-only) ----------------
HIDDEN = 12
LAM_ADV = 1.0
LR = 1e-3
EPOCHS = 300
SEED = 20260805


def family_of(task: str) -> str:
    for sep in (".", ":"):
        if sep in task:
            return task.split(sep, 1)[0]
    return task


def train_probe(cd_tr, y_tr, fam_tr, device):
    import torch
    from torch import nn

    class _Rev(torch.autograd.Function):
        @staticmethod
        def forward(ctx, t):
            return t.clone()

        @staticmethod
        def backward(ctx, g):
            return -g  # gradient reversal (Ganin) : la branche famille reçoit −∇

    torch.manual_seed(SEED)
    enc = nn.Linear(cd_tr.shape[1], HIDDEN).to(device)
    head = nn.Linear(HIDDEN, 2).to(device)
    fam_vals = sorted(set(fam_tr.tolist()))
    fam_head = nn.Linear(HIDDEN, len(fam_vals)).to(device)
    fam_idx = {f: i for i, f in enumerate(fam_vals)}
    ft = torch.tensor([fam_idx[f] for f in fam_tr.tolist()], device=device)
    X = torch.as_tensor(cd_tr, dtype=torch.float32, device=device)
    y = torch.tensor(y_tr, dtype=torch.long, device=device)
    opt = torch.optim.Adam(list(enc.parameters()) + list(head.parameters())
                           + list(fam_head.parameters()), lr=LR)
    ce = nn.CrossEntropyLoss()
    for _ in range(EPOCHS):
        z = enc(X)
        lo = ce(head(z), y)
        la = ce(fam_head(_Rev.apply(z)), ft)
        loss = lo + LAM_ADV * la
        opt.zero_grad(); loss.backward(); opt.step()
    return enc, head


def main() -> int:
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pool = "v10"
    rows = json.loads((PILOT / f"latent-pool-{pool}.json").read_text())
    d = np.load(PILOT / f"latent-pool-{pool}.npz")
    y = np.array([int(r["y"]) for r in rows])
    tasks = np.array([r["task"] for r in rows])
    fams = np.array([family_of(t) for t in tasks])
    cd = s11.norm(s11.norm(d["E_state"]) + s11.norm(d["E_diff"]))

    scores = np.full(len(y), np.nan)
    preds = np.full(len(y), -1)
    skipped = {}
    for g in sorted(set(fams)):
        te = fams == g
        tr = ~te
        if not y[tr].any() or y[tr].all():
            skipped[g] = "train mono-classe"
            continue
        enc, head = train_probe(cd[tr], y[tr], fams[tr], device)
        with torch.no_grad():
            Xtr = torch.as_tensor(cd[tr], dtype=torch.float32, device=device)
            thr = float(torch.median(head(enc(Xtr))[:, 1]).item())  # seuil TRAIN seul
            Xte = torch.as_tensor(cd[te], dtype=torch.float32, device=device)
            s_te = head(enc(Xte))[:, 1].cpu().numpy()
        scores[te] = s_te
        preds[te] = (s_te > thr).astype(int)
        print(f"  fold {g[:28]:28} n={int(te.sum())}", flush=True)

    valid = ~np.isnan(scores)
    auc_ext = s11.auc(scores[valid][y[valid] == 1], scores[valid][y[valid] == 0])
    acc_ext = float((preds[valid] == y[valid]).mean())
    f1_in = s11._loao_f1_features(cd, tasks, y)
    auc_in = s11.auc(f1_in[y == 1], f1_in[y == 0])
    acc_in = float(((f1_in > np.median(f1_in)).astype(int) == y).mean())

    BASE_EXT, MARGIN, HOME_GUARD = 0.5477, 0.05, 0.6694 - 0.02
    pass_transfer = bool(auc_ext >= BASE_EXT + MARGIN)
    pass_home = bool(auc_in >= HOME_GUARD)
    verdict = ("FRANCHIT les gates — enregistré pour validation prospective "
               "(promotion JAMAIS sur le pool qui l'a testée, leçon S13)"
               if (pass_transfer and pass_home) else
               "SOUS LA GATE — résultat négatif publié, non promu")

    report = {
        "story": "13.3-family-adversarial-probe",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "pool": f"latent-pool-{pool}",
        "pool_sha256_16": sha256(
            (PILOT / f"latent-pool-{pool}.json").read_bytes()).hexdigest()[:16],
        "device": device,
        "config_pinned": {"hidden": HIDDEN, "lambda_adv": LAM_ADV, "lr": LR,
                          "epochs": EPOCHS, "seed": SEED,
                          "params_approx": 768 * HIDDEN + HIDDEN * 2,
                          "note": "épinglée pré-run, amendment-only (gates 13.1); "
                                  "un seul point de config — pas de grille"},
        "candidate": {
            "ext_loao": {"auc": round(auc_ext, 4), "acc": round(acc_ext, 4),
                         "n_evaluated": int(valid.sum()),
                         "folds_skipped": skipped},
            "in_family_loao": {"auc": round(auc_in, 4), "acc": round(acc_in, 4)},
        },
        "gates_sealed_13_1": {"baseline_ext": BASE_EXT, "margin": MARGIN,
                              "transfer_threshold": BASE_EXT + MARGIN,
                              "home_guard": round(HOME_GUARD, 4),
                              "pass_transfer": pass_transfer, "pass_home": pass_home},
        "verdict": verdict,
        "precedents": {"E2_S9": "capacité non bornée détruit le home regime ; ici "
                                "≈9.2k params et home-guard mesurée",
                       "S13": "promotion prospective seulement",
                       "LOAO_strict": "seuils réappris par fold sur train seul"},
        "serving": "non servi — géométrie v10 inchangée",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"advprobe ext-LOAO: AUC {auc_ext:.4f} acc {acc_ext:.4f} "
          f"(gate ≥ {BASE_EXT + MARGIN}) | in-family {auc_in:.4f} (garde ≥ {HOME_GUARD:.4f})")
    print(f"verdict: {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
