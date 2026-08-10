"""Scoring — la recette mesurée, rien de plus, rien de moins.

Procédure validée en LOAO (S3 08-10f, S7 08-10g) :
  GOLD : energy = 1 − cos(norm(s+d), norm(s+g)) — but gold REQUIS (G1 : but
         emprunté = mort), donc goal_text doit porter la destination réelle
         (énoncé de tests / problem statement).
  F1   : attracteur d'échecs sur composites du pool — zéro notion de but.
  GxF  : logreg λ=1 sur [−energy, f1] standardisés (mu/sd du pool de PROD —
         ce n'est pas une fuite : ce sont les constantes du modèle ; la
         procédure a été validée out-of-fold).

Abstention : quantiles de confiance (|p−0.5|) mesurés OUT-OF-FOLD par
calibrate.py et stockés hashés dans model.json. Jamais recalculés à chaud.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

DEFAULT_MODEL_JSON = Path(os.environ.get(
    "LI_MODEL_JSON",
    Path(__file__).resolve().parents[2] / "public" / "artifacts" / "model.json"))


def sigmoid(z: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def norm_rows(A: np.ndarray) -> np.ndarray:
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


class GateModel:
    """Poids + seuils, chargés d'un JSON hashé (jamais fittés à chaud)."""

    def __init__(self, path: Path | None = None):
        p = Path(path or DEFAULT_MODEL_JSON)
        spec = json.loads(p.read_text())
        self.w = np.array(spec["gxf"]["w"], dtype=float)      # 2 poids
        self.b = float(spec["gxf"]["b"])                       # biais
        self.feat_mu = np.array(spec["gxf"]["feat_mu"])
        self.feat_sd = np.array(spec["gxf"]["feat_sd"])
        self.q_low = float(spec["abstention"]["q50"])          # conf médiane
        self.q_high = float(spec["abstention"]["q75"])         # quart haut
        self.pool_sha256 = spec["pool_sha256"]
        self.recipe = spec.get("recipe", "gxf-logreg-l1")
        self._raw = p.read_bytes()
        self.sha256 = hashlib.sha256(self._raw).hexdigest()

    def combine(self, energy: float, f1: float) -> tuple[float, float, str]:
        """Retourne (p_pass, confiance, tier) ; tier ∈ high|mid|low."""
        feats = (np.array([-energy, f1]) - self.feat_mu) / self.feat_sd
        p = float(sigmoid(float(self.w @ feats + self.b)))
        conf = abs(p - 0.5)
        tier = "high" if conf >= self.q_high else (
            "mid" if conf >= self.q_low else "low")
        return p, conf, tier


def energy_gold(e_s: np.ndarray, e_d: np.ndarray, e_g: np.ndarray) -> float:
    cd = e_s + e_d
    cd /= (np.linalg.norm(cd) + 1e-9)
    cg = e_s + e_g
    cg /= (np.linalg.norm(cg) + 1e-9)
    return float(1.0 - float(cd @ cg))


def f1_attractor(c_query: np.ndarray, cd_pool: np.ndarray,
                 y_pool: np.ndarray, keep: np.ndarray | None = None
                 ) -> float:
    """d(fail le plus proche) − d(pass le plus proche), pool éventuellement
    filtré (exclude_task). Haut = proche des succès."""
    cd = cd_pool if keep is None else cd_pool[keep]
    y = y_pool if keep is None else y_pool[keep]
    sims = cd @ c_query
    if not (y == 0).any() or not (y == 1).any():
        return float("nan")
    d_fail = float((1 - sims[y == 0]).min())
    d_pass = float((1 - sims[y == 1]).min())
    return d_fail - d_pass
