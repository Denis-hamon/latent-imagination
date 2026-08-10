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

POOL_DIR_ENV = "LI_POOL_DIR"
POOL_NAME_ENV = "LI_POOL_NAME"


def _pool_dir() -> Path:
    return Path(os.environ.get(
        POOL_DIR_ENV,
        "/Users/dhamon/Desktop/wo/latent-imagination/data/landing/act2-pilot"))


def _pool_name() -> str:
    return os.environ.get(POOL_NAME_ENV, "latent-pool-v6")


def _norm(A: np.ndarray) -> np.ndarray:
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


class Pool:
    def __init__(self, pool_dir: Path | None = None):
        d = Path(pool_dir) if pool_dir else _pool_dir()
        name = _pool_name()
        rows = json.loads((d / f"{name}.json").read_text())
        z = np.load(d / f"{name}.npz")
        assert len(rows) == z["E_state"].shape[0], "pool json/npz désalignés"
        self.rows = rows
        self.y = np.array([int(r["y"]) for r in rows])
        self.tasks = np.array([r["task"] for r in rows])
        self.E_s = _norm(z["E_state"])
        E_d = _norm(z["E_diff"])
        self.cd = _norm(self.E_s + E_d)
        self.cg = _norm(self.E_s + _norm(z["E_goal"]))
        self.sha256 = hashlib.sha256(
            (d / f"{name}.json").read_bytes()
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
