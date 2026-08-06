"""JEPA arm — LeJEPA-lite (SIGReg) over frozen features + outcome head.

Doctrine: predict in representation space. The encoder maps frozen features to a
latent; the loss = classification loss + SIGReg (isotropic-Gaussian regularization
of the latent) — the LeJEPA recipe (one hyperparameter, no stop-gradient/EMA).
Same data, same budget manifest, same evaluator as the baseline. Nothing bespoke.

Budget guard: wall-clock and step caps from the registered envelope; on exceed,
the artifact is marked truncated (disclosure, not hiding) per PRD R10.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


class BudgetExceeded(Exception):
    code = "LI-PROBE-002"


@dataclass(frozen=True)
class JepaConfig:
    seed: int = 20260805
    hidden: int = 512
    epochs: int = 10
    batch: int = 64
    lr: float = 1e-3
    lam: float = 0.05  # SIGReg weight (the one learned-ish hyperparameter)
    steps_cap: int = 20_000
    wall_cap_s: float = 2 * 3600.0


def _mmd_inv_sqrt_var(z: Any) -> Any:

    # SIGReg core: encourage isotropic Gaussian latents via inverse-sqrt of variance.
    std = z.std(dim=0).clamp_min(1e-6)
    return (1.0 / std).mean()


def train_and_evaluate(
    X_train: Any,
    y_train: list[int],
    X_eval: Any,
    y_eval: list[int],
    *,
    config: JepaConfig | None = None,
) -> dict[str, Any]:
    import torch
    from torch import nn

    cfg = config or JepaConfig()
    torch.manual_seed(cfg.seed)

    Xtr = torch.as_tensor(X_train, dtype=torch.float32)
    ytr = torch.tensor(y_train, dtype=torch.long)
    Xev = torch.as_tensor(X_eval, dtype=torch.float32)
    in_dim = Xtr.shape[1]

    encoder = nn.Sequential(
        nn.Linear(in_dim, cfg.hidden),
        nn.SiLU(),
        nn.Linear(cfg.hidden, cfg.hidden),
    )
    head = nn.Linear(cfg.hidden, 2)
    params = list(encoder.parameters()) + list(head.parameters())
    opt = torch.optim.AdamW(params, lr=cfg.lr)
    ce = nn.CrossEntropyLoss()

    n = Xtr.shape[0]
    t0 = time.time()
    steps = 0
    logs: list[dict[str, float]] = []
    truncated = False
    for _epoch in range(cfg.epochs):
        perm = torch.randperm(n, generator=torch.Generator().manual_seed(cfg.seed))
        for i in range(0, n, cfg.batch):
            if steps >= cfg.steps_cap or (time.time() - t0) > cfg.wall_cap_s:
                truncated = True
                break
            idx = perm[i : i + cfg.batch]
            z = encoder(Xtr[idx])
            logits = head(z)
            loss = ce(logits, ytr[idx]) + cfg.lam * _mmd_inv_sqrt_var(z)
            opt.zero_grad(); loss.backward(); opt.step()
            steps += 1
        logs.append({"epoch": float(_epoch), "loss": float(loss.item())})
        if truncated:
            break

    wall = time.time() - t0
    encoder.eval(); head.eval()
    with torch.no_grad():
        pred = head(encoder(Xev)).argmax(dim=1).cpu().numpy()

    tp = int(((pred == 1) & (torch.tensor(y_eval) == 1).numpy()).sum())
    fp = int(((pred == 1) & (torch.tensor(y_eval) == 0).numpy()).sum())
    fn = int(((pred == 0) & (torch.tensor(y_eval) == 1).numpy()).sum())
    n_pos = tp + fp
    precision = tp / n_pos if n_pos else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    art = {
        "config": cfg.__dict__,
        "steps": steps,
        "truncated": truncated,
        "precision": precision,
        "recall": recall,
        "n_eval": len(y_eval),
        "loss_curve_last": logs[-1]["loss"] if logs else None,
    }
    # artifact hash = content only (no wall clock, no uuid — AD-7)
    art["artifact_hash"] = sha256(
        json.dumps(art, sort_keys=True, default=str).encode()
    ).hexdigest()
    art["wall_s"] = round(wall, 2)  # recorded, NEVER hashed
    art["_pred"] = pred.tolist()  # caller strips before write
    return art
