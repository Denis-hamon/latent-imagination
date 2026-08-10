"""PoolStore — charge le pool latent (artefact hors-git, hashé).

Format attendu (produit par scripts/act2/s7_pool_boltzmann.py) :
  latent-pool-v6.json : [{task, arm, campaign, state, diff, gold, y}, ...]
  latent-pool-v6.npz  : E_state, E_diff, E_goal (float32, même ordre)
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

DEFAULT_POOL_DIR = Path(
    os.environ.get("LI_POOL_DIR",
                   "/Users/dhamon/Desktop/wo/latent-imagination/data/landing/act2-pilot"))
POOL_NAME = os.environ.get("LI_POOL_NAME", "latent-pool-v6")


def _norm(A: np.ndarray) -> np.ndarray:
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


class Pool:
    def __init__(self, pool_dir: Path | None = None):
        d = Path(pool_dir or DEFAULT_POOL_DIR)
        rows = json.loads((d / f"{POOL_NAME}.json").read_text())
        z = np.load(d / f"{POOL_NAME}.npz")
        assert len(rows) == z["E_state"].shape[0], "pool json/npz désalignés"
        self.rows = rows
        self.y = np.array([int(r["y"]) for r in rows])
        self.tasks = np.array([r["task"] for r in rows])
        self.E_s = _norm(z["E_state"])
        E_d = _norm(z["E_diff"])
        self.cd = _norm(self.E_s + E_d)                    # composites (état ∘ action)
        self.cg = _norm(self.E_s + _norm(z["E_goal"]))     # composites (état ∘ but)
        self.sha256 = hashlib.sha256(
            (d / f"{POOL_NAME}.json").read_bytes()
            + z["E_state"].tobytes()).hexdigest()

    def comask(self, exclude_task: str | None) -> np.ndarray:
        if not exclude_task:
            return np.ones(len(self.rows), dtype=bool)
        return self.tasks != exclude_task


_pool: Pool | None = None


def get_pool() -> Pool:
    global _pool
    if _pool is None:
        _pool = Pool()
    return _pool
